"""Intervals, same-timepoint windows, causal context, and recording audit."""
import json
import math
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np

import csi_io as io

VERSION = '6.0-review'
CONTEXT_S = 8.0  # Current 2 s plus preceding 6 s.


def validate_config(config):
    if config.get('version') != VERSION or config.get('task') != io.TASK:
        raise ValueError('Use the V6 interval manifest with the V6 program')
    if config.get('window_s') != 2 or config.get('context_s') != CONTEXT_S:
        raise ValueError('This fixed comparison uses 2-second and 8-second windows')
    names = set()
    for item in config['records']:
        if item['file'] in names:
            raise ValueError('Duplicate manifest filename: ' + item['file'])
        names.add(item['file'])
        if type(item['include']) is not bool:
            raise ValueError('include must be true or false')
        if not isinstance(item['group_id'], str) or not item['group_id']:
            raise ValueError('Nonempty group_id required')
        for key in ('anchor_s', 'signal_start_s', 'end_trim_s'):
            v = item[key]
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0:
                raise ValueError('Invalid ' + key)
        if item['include'] and item['review_status'].startswith('pending'):
            raise ValueError('Pending annotation must not be included: ' + item['file'])
        if item['include'] and not item['intervals']:
            raise ValueError('Included recording needs at least one label interval')
        previous_end = -1.
        for interval in item['intervals']:
            start, end, label = interval['start_s'], interval['end_s'], interval['label']
            if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
                raise ValueError('Invalid interval start')
            if end is not None and (isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end) or end <= start):
                raise ValueError('Invalid interval end')
            if start < previous_end:
                raise ValueError('Intervals must be sorted and non-overlapping')
            if type(label) is not int or label not in (0, 1):
                raise ValueError('Interval label must be integer 0 or 1; unknown time is omitted')
            if not isinstance(interval.get('evidence'), str) or not interval['evidence'].strip():
                raise ValueError('Record the external evidence for every label interval')
            previous_end = float('inf') if end is None else end
    return config


def truth_for(start, end, intervals):
    """Only fully covered windows count; crossing a boundary is never majority-labelled."""
    for interval in intervals:
        right = float('inf') if interval['end_s'] is None else interval['end_s']
        if start >= interval['start_s'] - 1e-9 and end <= right + 1e-9:
            return interval['label']
    return None


def check_span(t, seq, a, start, end):
    ix = np.flatnonzero((t >= start) & (t < end))
    seconds = end - start
    issues = []
    if not 90 * seconds <= len(ix) <= 110 * seconds:
        issues.append('frame_count')
    if len(ix) < 2:
        issues.append('too_few_frames')
    else:
        if t[ix[-1]] - t[ix[0]] < seconds - .1:
            issues.append('time_coverage')
        if np.max(np.diff(t[ix])) > .05:
            issues.append('time_gap')
        if np.any(np.diff(seq[ix]) != 1):
            issues.append('sequence_gap')
        if not np.isfinite(a[ix]).all():
            issues.append('nonfinite_amplitude')
    return ix, ';'.join(issues)


def window_rows(t, seq, a, item):
    """Prediction construction never reads truth intervals or include/review flags.

    At startup/gaps, both algorithms use the same 2-s prediction. The context
    branch becomes available only after 8 s of reliable, past-and-present CSI.
    """
    rows = []
    signal_start = item.get('signal_start_s', item['anchor_s'])
    stop = t[-1] - item['end_trim_s'] - 2. + 1e-8
    for start in np.arange(item['anchor_s'], stop, 2.):
        if start < signal_start - 1e-9:
            continue
        end = start + 2.
        ix, error = check_span(t, seq, a, start, end)
        cstart = end - CONTEXT_S
        hix, herror = check_span(t, seq, a, cstart, end)
        if cstart < max(t[0], signal_start) - 1e-9:
            herror = 'startup'
        x = io.features(a[ix]) if not error else None
        history = io.features(a[hix]) if not error and not herror else None
        rows.append(dict(start_s=float(start), end_s=float(end), frames=len(ix),
                         quality='rejected' if error else 'accepted', reason=error,
                         context_start_s=float(cstart), context_ready=history is not None,
                         context_reason=herror if not error else 'current_window_rejected',
                         dynamic=x,
                         multiscale=np.concatenate((x, history)) if history is not None else None))
    return rows


def recording_rows(t, seq, a, item):
    rows = window_rows(t, seq, a, item)
    for row in rows:
        truth = truth_for(row['start_s'], row['end_s'], item['intervals'])
        # Labels define only sample eligibility, never numerical features or inference.
        history_truth = truth_for(row['context_start_s'], row['end_s'], item['intervals'])
        eligible = item['include'] and row['quality'] == 'accepted' and truth is not None
        row.update(file=item['file'], group_id=item['group_id'], fold=item['fold'],
                   truth=truth, included=item['include'], review_status=item['review_status'],
                   scoring_eligible=bool(eligible),
                   context_training_eligible=bool(eligible and row['context_ready'] and history_truth == truth))
    return rows


def read_archive(archive, manifest):
    config = validate_config(json.loads(Path(manifest).read_text(encoding='utf-8')))
    records, raw = [], {}
    with zipfile.ZipFile(archive) as z:
        files = {}
        for info in z.infolist():
            name = io.archive_name(info)
            parts = PurePosixPath(name).parts
            if info.is_dir() or any(p.startswith('.') or p == '__MACOSX' for p in parts):
                continue
            if name.lower().endswith('.jsonl'):
                base = PurePosixPath(name).name
                if base in files:
                    raise ValueError('Duplicate JSONL basename: ' + base)
                files[base] = info
        expected = {r['file'] for r in config['records']}
        if set(files) != expected:
            raise ValueError('ZIP/manifest JSONL names differ: ' + str(set(files) ^ expected))
        seen_hashes, seen_ids = set(), set()
        for item in config['records']:
            meta, t, seq, a, audit = io.read_record(z.read(files[item['file']]))
            if item['include']:
                if audit['raw_sha256'] in seen_hashes or audit['session_id'] in seen_ids:
                    raise ValueError('Duplicate recording content/session')
                seen_hashes.add(audit['raw_sha256']); seen_ids.add(audit['session_id'])
            rows = recording_rows(t, seq, a, item)
            records.extend(rows)
            audit.update(file=item['file'], included=item['include'], group_id=item['group_id'],
                         review_status=item['review_status'], windows=len(rows),
                         eligible_windows=sum(r['scoring_eligible'] for r in rows),
                         context_training_windows=sum(r['context_training_eligible'] for r in rows),
                         unknown_label_windows=sum(r['truth'] is None for r in rows),
                         rejected_windows=sum(r['quality'] == 'rejected' for r in rows))
            raw[item['file']] = dict(t=t, seq=seq, a=a, meta=meta, audit=audit, item=item)
    return config, raw, records


def metadata_rows(rows):
    return [{k: v for k, v in row.items() if k not in ('dynamic', 'multiscale')} for row in rows]


def audit_outputs(config, raw, rows, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    audits = [v['audit'] for v in raw.values()]
    io.write_json(output / 'manifest_used.json', config)
    io.write_csv(output / 'recording_audit.csv', audits)
    io.write_csv(output / 'window_audit.csv', metadata_rows(rows))
    pending = [r['file'] for r in config['records'] if r['review_status'].startswith('pending')]
    summary = dict(version=VERSION, pending_annotations=pending,
                   training_blocked=bool(pending),
                   eligible_windows=sum(r['scoring_eligible'] for r in rows),
                   context_training_windows=sum(r['context_training_eligible'] for r in rows),
                   independent_test_available=False,
                   scores_computed=False,
                   note='Historical V5 fits predate the user-specified 15-second crop for both empty recordings. '
                        'Historical scores cannot be reused as corrected validation. Both methods must be retrained.')
    io.write_json(output / 'audit_summary.json', summary)
    return summary
