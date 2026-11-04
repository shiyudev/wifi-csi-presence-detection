"""Four predeclared candidates, three trained forests, and exact save verification."""
import io as buffer_io
import os
import platform
import tempfile
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier

VERSION = '9.0-nov03-train15'
TASK = 'effective_zone_occupancy'
SEEDS = (0, 42, 123)
CANDIDATES = {
    'v6_rf': dict(feature='dynamic', threshold=.5),
    'rf_threshold_060': dict(feature='dynamic', threshold=.6),
    'common_rf': dict(feature='common', threshold=.5),
    'common_median_rf': dict(feature='common_median', threshold=.5),
}


def estimator(seed):
    return RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=3,
                                  class_weight='balanced', random_state=seed, n_jobs=1)


def fit_models(rows, seed):
    if not rows or any(not r['scoring_eligible'] for r in rows):
        raise ValueError('Training needs eligible, correctly annotated windows')
    if {r['truth'] for r in rows} != {0, 1}:
        raise ValueError('Both classes required for training')
    labels = np.array([r['truth'] for r in rows], int)
    return {kind: estimator(seed).fit(np.array([r[kind] for r in rows]), labels)
            for kind in ('dynamic', 'common', 'common_median')}


def infer(models, rows):
    if not rows or any(r['quality'] != 'accepted' for r in rows):
        raise ValueError('Predict accepted windows; preserve rejected windows as unknown')
    scores = {}
    for kind, model in models.items():
        scores[kind] = model.predict_proba(np.array([r[kind] for r in rows]))[:, list(model.classes_).index(1)]
    outputs = {}
    for name, spec in CANDIDATES.items():
        score = scores[spec['feature']]
        # For classes [0,1], ties at .5 match sklearn's default class 0.
        pred = (score > spec['threshold']).astype(int)
        outputs[name] = (pred, score)
    return outputs


def metrics(y, prediction):
    y, prediction = np.asarray(y, int), np.asarray(prediction, int)
    if not len(y):
        return None
    n0, n1 = int(np.sum(y == 0)), int(np.sum(y == 1))
    fp, fn = int(np.sum((y == 0)&(prediction == 1))), int(np.sum((y == 1)&(prediction == 0)))
    return dict(windows=len(y), correct=int(np.sum(y == prediction)), accuracy=float(np.mean(y == prediction)),
        false_positive_rate=fp/n0 if n0 else None, false_negative_rate=fn/n1 if n1 else None,
        balanced_accuracy=((1-fp/n0)+(1-fn/n1))/2 if n0 and n1 else None,
        confusion_matrix=[[n0-fp, fp], [fn, n1-fn]])


def state_for(models, rows, raw, seed, role, default_candidate='v6_rf'):
    names = sorted({r['file'] for r in rows})
    return dict(version=VERSION, task=TASK, models=models, seed=seed, role=role,
        candidate_specs=CANDIDATES, default_candidate=default_candidate,
        training_files=names, training_raw_sha256=[raw[n]['audit']['raw_sha256'] for n in names],
        training_session_ids=[raw[n]['audit']['session_id'] for n in names],
        window_s=2., score_kind='uncalibrated_class_score',
        versions=dict(python=platform.python_version(), sklearn=sklearn.__version__,
                      numpy=np.__version__, joblib=joblib.__version__))


def save_verified(state, path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    stream = buffer_io.BytesIO(); joblib.dump(state, stream, compress=3)
    payload = stream.getvalue(); tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', suffix='.tmp', delete=False) as f:
            tmp = Path(f.name); f.write(payload); f.flush(); os.fsync(f.fileno())
        restored = joblib.load(tmp)
        before, after = infer(state['models'], rows), infer(restored['models'], rows)
        for candidate in CANDIDATES:
            for a, b in zip(before[candidate], after[candidate]):
                if not np.array_equal(a, b):
                    raise AssertionError('Saved prediction or score changed')
        os.replace(tmp, path)
        if path.read_bytes() != payload:
            raise IOError('Saved bytes changed')
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def load(path):
    state = joblib.load(path)  # Trusted project files only; joblib uses pickle.
    if state.get('version') != VERSION or state.get('task') != TASK or state.get('candidate_specs') != CANDIDATES:
        raise ValueError('Use V9 models with the matching V9 program')
    if state['versions']['sklearn'] != sklearn.__version__:
        raise ValueError('Install the versions in requirements.txt')
    return state
