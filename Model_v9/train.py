"""Refit the fixed forests on all twenty authorized recordings; no heldout claim."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import csi_io as io
import models_v9 as model
from dataset_v9 import TRAIN_NAMES, read_training


def run(archives, manifest, output, plan_path):
    root = Path(__file__).resolve().parent
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    for relative, expected in plan['source_hashes'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen training source changed: ' + relative)
    if hashlib.sha256(Path(manifest).read_bytes()).hexdigest() != plan['source_hashes']['labels_train.json']:
        raise ValueError('Use the frozen training manifest')
    for archive in archives:
        if hashlib.sha256(Path(archive).read_bytes()).hexdigest() not in plan['archive_sha256'].values():
            raise ValueError('Unexpected source archive')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Choose a new, empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    config, raw, all_rows, log = read_training(archives, manifest)
    rows = [r for r in all_rows if r['scoring_eligible']]
    assert {r['file'] for r in rows} == TRAIN_NAMES
    fitted = model.fit_models(rows, plan['seed'])
    state = model.state_for(fitted, rows, raw, plan['seed'], 'all_twenty_training', plan['default_candidate'])
    state.update(training_scope='nov03_numbers_1_through_5', reserved_test_files=[],
                 test_evaluated=False, old_recordings_included=False,
                 promoted_holdout_files=[f for f in sorted(TRAIN_NAMES) if f.endswith('5.jsonl')],
                 training_plan_sha256=hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
                 frozen_at_utc=datetime.now(timezone.utc).isoformat())
    path = output / 'occupancy_model_v9.joblib'
    model.save_verified(state, path, rows)
    predictions = model.infer(model.load(path)['models'], rows)
    arrays = {k: np.array([r[k] for r in rows]) for k in ('dynamic','common','common_median')}
    arrays.update(truth=np.array([r['truth'] for r in rows], int), recording_file=np.array([r['file'] for r in rows]),
                  start_s=np.array([r['start_s'] for r in rows]), end_s=np.array([r['end_s'] for r in rows]))
    for name, (pred, score) in predictions.items():
        arrays[name+'_prediction'] = pred
        arrays[name+'_score'] = score
    np.savez_compressed(output/'training_verification.npz', **arrays)
    io.write_json(output/'manifest_used.json', config)
    io.write_json(output/'training_access_log.json', log)
    io.write_csv(output/'recording_audit.csv', [v['audit'] for v in raw.values()])
    io.write_csv(output/'window_audit.csv', [{k:v for k,v in r.items() if k not in
                  {'dynamic','multiscale','common','common_median'}} for r in all_rows])
    report = dict(version=model.VERSION, status='trained_and_frozen', training_files=len(raw),
        training_windows=len(rows), training_seconds=2*len(rows),
        added_windows=sum(r['file'].endswith('5.jsonl') for r in rows),
        occupied_windows=sum(r['truth']==1 for r in rows), unoccupied_windows=sum(r['truth']==0 for r in rows),
        by_activity={a:sum(r['activity']==a for r in rows) for a in sorted({r['activity'] for r in rows})},
        by_file={f:sum(r['file']==f for r in rows) for f in sorted(TRAIN_NAMES)},
        rejected_windows=sum(r['quality']=='rejected' for r in all_rows),
        default_candidate=state['default_candidate'], available_candidates=list(model.CANDIDATES),
        trained_forests=len(fitted), seed=plan['seed'], heldout_accuracy=None,
        independent_test_available=False, hyperparameter_search=False,
        features_and_estimator_parameters_changed=False, refit_from_all_raw_data=True,
        pictures_used_as_features=False, labels_from_predictions=False,
        source_hashes=plan['source_hashes'], model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        notes=['The former four holdout files are now training data.',
               'Old 1-4 labels unchanged, including filename-based video tails. New 5 tails excluded.',
               'Empty5 single-frame spike retained unchanged; no targeted cleanup.',
               'V8 historical test results cannot be used as V9 accuracy. New independent recordings required.'])
    io.write_json(output/'training_report.json', report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip',action='append',required=True,dest='archives')
    p.add_argument('--manifest',default='labels_train.json')
    p.add_argument('--out',default='results')
    p.add_argument('--plan',default='training_plan.json')
    a=p.parse_args();run(a.archives,a.manifest,a.out,a.plan)
