"""Frozen V9 prediction with optional constant truth, without updating models."""
import argparse
import math
from pathlib import Path

import numpy as np

import csi_io as io
from features_v7 import window_rows
import models_v9 as model


def seen_in_training(state, audit):
    return (audit['raw_sha256'] in state['training_raw_sha256']
            or audit['session_id'] in state['training_session_ids'])


def run(recording, model_path, output, candidate='default', start=1., truth=None):
    if not math.isfinite(start) or start < 0:
        raise ValueError('start must be a finite nonnegative number')
    if truth is not None and (type(truth) is not int or truth not in (0,1)):
        raise ValueError('truth must be 0 or 1')
    output = Path(output); summary_path = output.with_suffix('.summary.json')
    if output.exists() or summary_path.exists():
        raise FileExistsError('Choose a new output filename')
    state = model.load(model_path)
    chosen = state['default_candidate'] if candidate == 'default' else candidate
    if chosen not in (*model.CANDIDATES, 'all'):
        raise ValueError('Unknown candidate')
    _, t, seq, amplitude, audit = io.read_record(Path(recording).read_bytes())
    windows = window_rows(t,seq,amplitude,dict(anchor_s=1.,signal_start_s=start,end_trim_s=1.))
    valid = [r for r in windows if r['quality']=='accepted']
    if not valid:
        raise ValueError('No usable two-second windows')
    predictions = model.infer(state['models'], valid)
    rows, metrics = [], {}
    for name, (pred, scores) in predictions.items():
        if chosen != 'all' and chosen != name:
            continue
        for r,p,s in zip(valid,pred,scores):
            rows.append(dict(candidate=name,start_s=r['start_s'],end_s=r['end_s'],
                prediction=int(p),label='occupied' if p else 'unoccupied',model_score=float(s),
                threshold=model.CANDIDATES[name]['threshold'],quality='accepted',reason='',
                human_truth='' if truth is None else truth,correct='' if truth is None else bool(p==truth)))
        rows.extend(dict(candidate=name,start_s=r['start_s'],end_s=r['end_s'],prediction='',
            label='unknown',model_score='',threshold=model.CANDIDATES[name]['threshold'],
            quality='rejected',reason=r['reason'],human_truth='' if truth is None else truth,correct='')
            for r in windows if r['quality']!='accepted')
        if truth is not None:
            metrics[name]=model.metrics(np.full(len(valid),truth),pred)
    rows.sort(key=lambda r:(r['start_s'],r['candidate']))
    seen=seen_in_training(state,audit)
    summary=dict(version=model.VERSION,recording=Path(recording).name,candidate=chosen,
        start_s=start,accepted_windows=len(valid),rejected_windows=len(windows)-len(valid),
        seen_in_training=seen,evaluation_role='training_diagnostic' if seen else 'unseen_file_independence_requires_confirmation',
        metrics=metrics if truth is not None else None,model_updated=False,
        score_kind='uncalibrated_class_score',
        note='A constant truth is valid only when the entire selected portion has that state; '
             'it never changes predictions. This command cannot establish experiment independence.')
    output.parent.mkdir(parents=True,exist_ok=True)
    io.write_csv(output,rows);io.write_json(summary_path,summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('recording')
    p.add_argument('--model',default='results/occupancy_model_v9.joblib')
    p.add_argument('--candidate',choices=['default','all',*model.CANDIDATES],default='default')
    p.add_argument('--out',default='predictions.csv')
    p.add_argument('--start',type=float,default=1.)
    p.add_argument('--truth',type=int,choices=[0,1])
    args=p.parse_args()
    import json
    print(json.dumps(run(args.recording,args.model,args.out,args.candidate,args.start,args.truth),ensure_ascii=False,indent=2))
