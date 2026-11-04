"""Read only the twenty authorized training recordings from both source ZIPs."""
import json
import re
import zipfile
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

import csi_io as io
from data_v6 import validate_config, recording_rows
from features_v7 import add_features

SCENES = ('无人', '门外走动', '玩电脑', '走动')
TRAIN_NAMES = frozenset(f'{scene}{n}.jsonl' for scene in SCENES for n in (1, 2, 3, 4, 5))
RESERVED_NAMES = frozenset()


def training_blobs(archives, access_log):
    """The central directory may be listed; all twenty authorized payloads are opened."""
    with ExitStack() as stack:
        members = {}
        for path in archives:
            z = stack.enter_context(zipfile.ZipFile(path))
            for info in z.infolist():
                name = io.archive_name(info)
                parts = PurePosixPath(name).parts
                if info.is_dir() or any(p.startswith('.') or p == '__MACOSX' for p in parts):
                    continue
                if not name.lower().endswith('.jsonl'):
                    continue
                base = PurePosixPath(name).name
                if base in members:
                    raise ValueError('Duplicate recording basename: ' + base)
                members[base] = (z, info)
        if set(members) != TRAIN_NAMES | RESERVED_NAMES:
            raise ValueError('Expected exactly four scenes numbered 1 through 5')
        for name in sorted(TRAIN_NAMES):
            z, info = members[name]
            # Do not put this read before the explicit allow-list selection.
            payload = z.read(info)
            access_log.append(dict(file=name, member=info.filename, role='training'))
            yield name, payload


def load_config(path):
    config = validate_config(json.loads(Path(path).read_text(encoding='utf-8')))
    if {r['file'] for r in config['records']} != TRAIN_NAMES:
        raise ValueError('Training manifest must contain only the twenty number 1-5 files')
    for item in config['records']:
        if not item['include']:
            raise ValueError('All twenty specified recordings must be included')
        scene = re.fullmatch(r'(无人|门外走动|玩电脑|走动)[1-5]\.jsonl', item['file']).group(1)
        labels = [i['label'] for i in item['intervals']]
        activities = [i.get('activity') for i in item['intervals']]
        if scene in ('无人', '门外走动'):
            middle = 'empty' if scene == '无人' else 'outside_walking'
            if labels != [1, 0, 1] or activities != ['departure', middle, 'arrival']:
                raise ValueError('Use confirmed departure / empty / arrival intervals: ' + item['file'])
        elif any(value != 1 for value in labels):
            raise ValueError('Indoor occupied scene label mismatch: ' + item['file'])
    return config


def read_training(archives, manifest):
    config = load_config(manifest)
    items = {r['file']: r for r in config['records']}
    raw, rows, access_log = {}, [], []
    hashes, sessions = set(), set()
    for name, payload in training_blobs(archives, access_log):
        meta, t, seq, amplitude, audit = io.read_record(payload)
        if audit['raw_sha256'] in hashes or audit['session_id'] in sessions:
            raise ValueError('Repeated training recording content/session')
        hashes.add(audit['raw_sha256']); sessions.add(audit['session_id'])
        item = items[name]
        current = recording_rows(t, seq, amplitude, item)
        for r in current:
            matched = next((i for i in item['intervals']
                if r['start_s'] >= i['start_s'] and
                   (i['end_s'] is None or r['end_s'] <= i['end_s'])), None)
            r['activity'] = matched['activity'] if matched else 'transition_boundary_excluded'
            video_end = item.get('video_end_s')
            r['video_coverage'] = ('not_available' if video_end is None else
                'covered' if r['end_s'] <= video_end else
                'uncovered_tail' if r['start_s'] >= video_end else 'partly_covered')
        # Only selected, accepted intervals need numeric common features.
        eligible = [r for r in current if r['scoring_eligible']]
        if not eligible:
            raise ValueError('No usable labeled windows: ' + name)
        add_features(eligible, t, amplitude)
        rows.extend(current)
        audit.update(file=name, selected_windows=len(eligible),
                     selected_seconds=2 * len(eligible),
                     rejected_windows=sum(r['quality'] == 'rejected' for r in current),
                     unlabeled_windows=sum(r['truth'] is None for r in current),
                     signal_start_s=item['signal_start_s'],
                     interval_end_s=item['intervals'][-1]['end_s'])
        raw[name] = dict(meta=meta, audit=audit, item=item)
    assert set(raw) == TRAIN_NAMES and not (set(raw) & RESERVED_NAMES)
    return config, raw, rows, access_log
