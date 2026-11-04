"""Verify labels, model serialization and unchanged 1-4 training features."""
import argparse
import hashlib
import io as buffer_io
import json
import zipfile
from pathlib import Path
import numpy as np
import csi_io as io
import models_v9 as model
from dataset_v9 import TRAIN_NAMES, load_config
from data_v6 import truth_for


def verify(output):
    root=Path(__file__).resolve().parent;output=Path(output)
    report=json.loads((output/'training_report.json').read_text(encoding='utf-8'))
    items={r['file']:r for r in load_config(output/'manifest_used.json')['records']}
    path=output/'occupancy_model_v9.joblib'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==report['model_sha256']
    for n,h in report['source_hashes'].items():assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
    state=model.load(path)
    assert set(state['training_files'])==TRAIN_NAMES and not state['reserved_test_files']
    assert len(set(state['training_raw_sha256']))==20 and len(set(state['training_session_ids']))==20
    log=json.loads((output/'training_access_log.json').read_text(encoding='utf-8'))
    assert len(log)==20 and {r['file'] for r in log}==TRAIN_NAMES
    with np.load(output/'training_verification.npz',allow_pickle=False) as saved:
        rows=[]
        for i,name in enumerate(saved['recording_file']):
            start,end=saved['start_s'][i],saved['end_s'][i]
            assert end-start==2
            assert truth_for(start,end,items[str(name)]['intervals'])==int(saved['truth'][i])
            rows.append(dict(quality='accepted',**{k:saved[k][i] for k in ('dynamic','common','common_median')}))
        for c,(pred,score) in model.infer(state['models'],rows).items():
            np.testing.assert_array_equal(pred,saved[c+'_prediction'])
            np.testing.assert_array_equal(score,saved[c+'_score'])
        oldmask=np.array([not str(n).endswith('5.jsonl') for n in saved['recording_file']])
        with zipfile.ZipFile(root/'history/CSI_Training_v8_Train14.zip') as z:
            old=np.load(buffer_io.BytesIO(z.read('CSI_Training_v8_Train14/results/training_verification.npz')),allow_pickle=False)
            for k in ('recording_file','start_s','end_s','truth','dynamic','common','common_median'):
                np.testing.assert_array_equal(saved[k][oldmask],old[k])
        assert int(oldmask.sum())==283 and int((~oldmask).sum())==62
    check=dict(status='passed',training_files=20,training_windows=len(rows),old_windows_unchanged=283,
        added_windows=62,reloaded_predictions_and_scores_verified=4*len(rows),
        heldout_accuracy=None,independent_test_available=False)
    io.write_json(output/'verification.json',check)
    print(json.dumps(check,ensure_ascii=False,indent=2));return check


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',default='results');verify(p.parse_args().results)
