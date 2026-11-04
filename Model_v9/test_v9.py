"""Focused tests for the requested holdout boundary and label/feature separation."""
import copy
import hashlib
import io as buffer_io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

import numpy as np

from dataset_v9 import SCENES, TRAIN_NAMES, RESERVED_NAMES, training_blobs, load_config
from data_v6 import recording_rows, truth_for
from features_v7 import add_features
import models_v9 as model


class Tests(unittest.TestCase):
    def test_all_twenty_payloads_are_included(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.zip'
            with zipfile.ZipFile(path, 'w') as z:
                for name in TRAIN_NAMES: z.writestr('folder/'+name, name.encode())
            log=[]
            read=list(training_blobs([path],log))
            self.assertEqual({n for n,_ in read},TRAIN_NAMES)
            self.assertEqual(len(read),20)
            self.assertEqual(sum(n.endswith('5.jsonl') for n,_ in read),4)

    def test_manifest_requires_all_twenty_files(self):
        source=Path(__file__).parent/'labels_train.json'
        config=json.loads(source.read_text(encoding='utf-8'))
        config['records']=[r for r in config['records'] if not r['file'].endswith('5.jsonl')]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'labels.json';path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):load_config(path)

    def test_new_video_tails_excluded(self):
        items={r['file']:r for r in load_config(Path(__file__).parent/'labels_train.json')['records']}
        for name,start,end in [('玩电脑5.jsonl',31,33),('走动5.jsonl',27,29)]:
            self.assertIsNone(truth_for(start,end,items[name]['intervals']))
            self.assertEqual(truth_for(start-2,end-2,items[name]['intervals']),1)

    def test_outside_scene_remains_unoccupied(self):
        config = load_config(Path(__file__).parent / 'labels_train.json')
        for item in config['records']:
            if item['file'].startswith(('无人', '门外走动')):
                self.assertEqual([i['label'] for i in item['intervals']], [1, 0, 1])
                self.assertEqual(item['intervals'][0]['activity'], 'departure')
                self.assertEqual(item['intervals'][2]['activity'], 'arrival')

    def test_cross_boundary_windows_are_excluded(self):
        spans = [dict(start_s=10.5, end_s=20.5, label=0)]
        self.assertIsNone(truth_for(9, 11, spans))
        self.assertIsNone(truth_for(19, 21, spans))
        self.assertEqual(truth_for(11, 13, spans), 0)

    def test_selected_features_ignore_discarded_edges(self):
        rng = np.random.default_rng(9)
        t = np.arange(0, 30, .01); seq = np.arange(len(t))
        a = 20 + rng.normal(0, .5, (len(t), 64))
        item = dict(file='synthetic', group_id='g', fold=0, include=True,
                    review_status='synthetic', anchor_s=1., signal_start_s=11., end_trim_s=1.,
                    intervals=[dict(start_s=11., end_s=21., label=0, evidence='synthetic')])
        def selected(amplitude, cfg):
            rows = [r for r in recording_rows(t, seq, amplitude, cfg) if r['scoring_eligible']]
            return add_features(rows, t, amplitude)
        before = selected(a, item)
        changed = a.copy(); changed[(t < 11) | (t >= 21)] = 1e9
        after = selected(changed, item)
        for x, y in zip(before, after):
            for kind in ('dynamic', 'common', 'common_median'):
                np.testing.assert_array_equal(x[kind], y[kind])
        other = copy.deepcopy(item); other['file'] = 'renamed'
        other['intervals'][0]['label'] = 1
        for x, y in zip(before, selected(a, other)):
            for kind in ('dynamic', 'common', 'common_median'):
                np.testing.assert_array_equal(x[kind], y[kind])

    def test_parameters_and_thresholds_are_fixed(self):
        forest = model.estimator(42)
        self.assertEqual(forest.n_estimators, 200)
        self.assertEqual(forest.max_depth, 5)
        self.assertEqual(forest.min_samples_leaf, 3)
        self.assertEqual(forest.random_state, 42)
        self.assertEqual(model.CANDIDATES['v6_rf']['threshold'], .5)
        self.assertEqual(model.CANDIDATES['common_rf']['threshold'], .5)
        self.assertEqual(model.CANDIDATES['rf_threshold_060']['threshold'], .6)


if __name__ == '__main__': unittest.main(verbosity=2)
