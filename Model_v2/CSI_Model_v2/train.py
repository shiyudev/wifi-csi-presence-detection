"""Exploratory effective-zone occupancy baseline. User-confirmed filename labels; no synchronized video."""
import argparse, csv, hashlib, json, platform, zipfile
from pathlib import Path
import numpy as np
import sklearn
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix

WINDOW = 2.0
TRIM = 1.0

def read_record(blob):
    rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
    meta = [r for r in rows if r.get('type') == 'metadata']
    summaries = [r for r in rows if r.get('type') == 'summary']
    frames = [r for r in rows if r.get('type') == 'csi']
    if len(meta) != 1 or len(summaries) != 1 or not frames:
        raise ValueError('Missing/duplicate metadata or summary, or empty recording')
    summary = summaries[0]
    if summary['status'] != 'complete' or summary['saved_records'] != len(frames):
        raise ValueError('Recording not complete or frame count mismatch')
    ticks = [int(r['device_capture_us']) for r in frames]
    t = np.array([(x-ticks[0])/1e6 for x in ticks])
    seq = np.array([int(r['sequence']) for r in frames], dtype=np.int64)
    if np.any(np.diff(t) <= 0) or np.any(np.diff(seq) <= 0):
        raise ValueError('Time/sequence is not strictly increasing')
    if any(r['subcarrier_count'] != 64 for r in frames):
        raise ValueError('v1 supports 64 subcarriers only')
    i = np.array([r['i'] for r in frames], dtype=float)
    q = np.array([r['q'] for r in frames], dtype=float)
    if i.shape != (len(frames),64) or q.shape != i.shape:
        raise ValueError('Invalid I/Q shape')
    a = np.hypot(i,q)
    if not np.isfinite(a).all():
        raise ValueError('Nonfinite samples')
    audit = dict(frames=len(frames), duration_s=float(t[-1]),
                 missing_sequences=int(np.sum(np.diff(seq)-1)),
                 max_gap_s=float(np.max(np.diff(t))), device=meta[0].get('device'),
                 initial_label=meta[0].get('initial_label'), label_verified=meta[0].get('label_verified'))
    return meta[0], t, seq, a, audit

def features(a):
    # Per-window normalization, not a fitted transform. Never use test data to fit preprocessing.
    relative = a / np.maximum(a.mean(axis=0), 1.0)
    delta = np.diff(relative, axis=0)
    return np.concatenate([relative.std(axis=0), np.mean(np.abs(delta),axis=0),
                           np.ptp(relative,axis=0), delta.std(axis=0)])

def windows(t, seq, a):
    out = []
    rejected = 0
    # Non-overlapping windows; trim the edges, without claiming transitions are thereby removed.
    for start in np.arange(TRIM, t[-1]-TRIM-WINDOW+1e-8, WINDOW):
        ix = np.flatnonzero((t >= start) & (t < start+WINDOW))
        if (len(ix) < 180 or len(ix) > 220 or t[ix[-1]]-t[ix[0]] < 1.9
            or np.max(np.diff(t[ix])) > .05 or np.any(np.diff(seq[ix]) != 1)):
            rejected += 1
            continue
        out.append((float(start),features(a[ix])))
    return out,rejected

def write_csv(path, rows):
    if not rows: return
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def train(archive, manifest, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    entries=json.loads(Path(manifest).read_text(encoding='utf-8'))
    samples=[]; audits=[]; ids={}; fingerprints={}; host_intervals=[]
    with zipfile.ZipFile(archive) as z:
        files={Path(n).name:n for n in z.namelist() if n.endswith('.jsonl')}
        if len(files)!=sum(n.endswith('.jsonl') for n in z.namelist()):
            raise ValueError('Duplicate filenames')
        for item in entries:
            blob=z.read(files[item['file']]);meta,t,seq,a,audit=read_record(blob)
            audit.update(file=item['file'],split=item['split'],label=item['label'],reason=item['reason'])
            audits.append(audit)
            if item['split']=='exclude':continue
            if item['label'] not in (0,1) or item['split'] not in ('train','test'):
                raise ValueError('Invalid label or split')
            for value,seen in [(meta['session_id'],ids),(hashlib.sha256(blob).hexdigest(),fingerprints)]:
                if value in seen: raise ValueError('Duplicate included recording')
                seen[value]=item['split']
            # Require simultaneous views to share a split; host wall clock is used for this check only.
            from datetime import datetime
            start=datetime.fromisoformat(meta['started_utc'].replace('Z','+00:00')).timestamp()
            end=start+t[-1]
            for s,e,split in host_intervals:
                if min(end,e)>max(start,s) and item['split']!=split:
                    raise ValueError('Overlapping sessions across train/test: group these together')
            host_intervals.append((start,end,item['split']))
            ws,rejected=windows(t,seq,a)
            audit.update(accepted_windows=len(ws),rejected_windows=rejected)
            for start,x in ws:samples.append(dict(file=item['file'],split=item['split'],label=item['label'],start_s=start,x=x))
    for audit in audits:
        audit.setdefault('accepted_windows',0);audit.setdefault('rejected_windows',0)
    write_csv(output/'audit.csv',audits)
    tr=[r for r in samples if r['split']=='train'];te=[r for r in samples if r['split']=='test']
    if {r['label'] for r in tr}!={0,1} or {r['label'] for r in te}!={0,1}:
        raise ValueError('Both train and test must contain both classes after quality filtering')
    assert not {r['file'] for r in tr}&{r['file'] for r in te}
    model=RandomForestClassifier(n_estimators=200,max_depth=5,min_samples_leaf=3,
                                  class_weight='balanced',random_state=42,n_jobs=-1)
    model.fit(np.array([r['x'] for r in tr]),[r['label'] for r in tr])
    x_test=np.array([r['x'] for r in te]);y=np.array([r['label'] for r in te])
    pred=model.predict(x_test);p=model.predict_proba(x_test)[:,list(model.classes_).index(1)]
    predictions=[dict(file=r['file'],start_s=r['start_s'],end_s=r['start_s']+WINDOW,
                      assigned_label=r['label'],prediction=int(h),occupancy_score=float(v))
                 for r,h,v in zip(te,pred,p)]
    write_csv(output/'test_predictions.csv',predictions)
    report=dict(status='development_evaluation_not_final', task='effective_zone_occupancy', label_source='user_confirmed_filenames_and_context', evaluation_role='reused_batch_development_holdout',train_windows=len(tr),test_windows=len(te),
                train_files=sorted({r['file'] for r in tr}),test_files=sorted({r['file'] for r in te}),
                accuracy=float(accuracy_score(y,pred)),balanced_accuracy=float(balanced_accuracy_score(y,pred)),
                confusion_matrix_rows_true_cols_pred_0_1=confusion_matrix(y,pred,labels=[0,1]).tolist(),
                majority_train_baseline_accuracy=float(np.mean(y==int(np.bincount([r['label'] for r in tr]).argmax()))),
                per_file={f:dict(windows=sum(r['file']==f for r in predictions),
                            accuracy=float(np.mean([r['prediction']==r['assigned_label'] for r in predictions if r['file']==f])))
                          for f in sorted({r['file'] for r in te})},
                limitations=['Labels assigned from user-confirmed filenames and scene context; exact transitions are not video-verified.',
                  'Only one device, room and collection day; only two empty-room recordings.',
                  'Target is occupancy within the designated effective zone, not the whole room. Fan-only and outside-door movement are negative. No verified long stationary/sleeping-person evaluation.',
                  'This batch was previously inspected and evaluated. Holdout results are development evidence, not a new blind final test. Zone boundary coordinates remain unspecified.',
                  'Occupancy score is not a calibrated probability. Architecture and hyperparameters unchanged from v1; no tuning on this evaluation.'],
                versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__),
                experiment_conditions=dict(door='open throughout batch 1',max_moving_objects=1,fan_during_person_walking='off',nonparticipants='outside effective zone',door_walk='outside room near door',zone_boundary='not measured'),
                labels_manifest_sha256=hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
                archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest())
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    joblib.dump(dict(model=model,window_s=WINDOW,trim_s=TRIM,feature_version='relative_amplitude_v1',
                     task='effective_zone_occupancy', labels={0:'unoccupied',1:'occupied'},report=report),output/'occupancy_model.joblib',compress=3)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

def predict(recording, model_path, output):
    # Only load trusted joblib files: pickle-based formats can execute code.
    bundle=joblib.load(model_path)
    if bundle.get('task') != 'effective_zone_occupancy':raise ValueError('This predictor requires an occupancy v2 model, not motion v1')
    if bundle['feature_version']!='relative_amplitude_v1':raise ValueError('Unknown feature version')
    _,t,seq,a,_=read_record(Path(recording).read_bytes());ws,rejected=windows(t,seq,a)
    if not ws:raise ValueError('No usable windows (needs complete 64-subcarrier recording near 100 Hz)')
    model=bundle['model'];x=np.array([w[1] for w in ws]);pr=model.predict(x)
    score=model.predict_proba(x)[:,list(model.classes_).index(1)]
    write_csv(output,[dict(start_s=w[0],end_s=w[0]+WINDOW,prediction=int(y),label=bundle['labels'][int(y)],occupancy_score=float(s)) for w,y,s in zip(ws,pr,score)])
    print(f'Saved {len(ws)} predictions; rejected {rejected} windows')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--zip');p.add_argument('--manifest',default='labels.json');p.add_argument('--out',default='results')
    p.add_argument('--predict');p.add_argument('--model',default='results/occupancy_model.joblib');p.add_argument('--predictions',default='predictions.csv');args=p.parse_args()
    if args.predict:predict(args.predict,args.model,args.predictions)
    elif args.zip:train(args.zip,args.manifest,args.out)
    else:p.error('Use --zip for training or --predict for inference')
