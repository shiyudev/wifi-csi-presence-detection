"""Raw CSI validation and two-second features preserved from V3/V5."""

import base64, csv, hashlib, json, math, struct

from pathlib import Path

import numpy as np

TASK = 'effective_zone_occupancy'

WINDOW_S = 2.0

CAP_REASON = '已达到 20 MB 记录上限，请导出后新开一段。'

LABELS = {0: 'unoccupied', 1: 'occupied'}

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def write_csv(path, rows):
    if not rows:
        return
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def archive_name(info):
    """Repair UTF-8 names incorrectly stored without the ZIP UTF-8 flag."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode('cp437').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name

def read_record(blob):
    rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
    metas = [r for r in rows if r.get('type') == 'metadata']
    summaries = [r for r in rows if r.get('type') == 'summary']
    frames = [r for r in rows if r.get('type') == 'csi']
    if len(metas) != 1 or len(summaries) != 1 or len(frames) < 2:
        raise ValueError('Missing/duplicate metadata/summary, or fewer than 2 frames')
    if rows[0].get('type') != 'metadata' or rows[-1].get('type') != 'summary':
        raise ValueError('Recording boundaries are incomplete')
    meta, summary = metas[0], summaries[0]
    if meta.get('source') != 'espectre.dev_real_CSI_V8' or meta.get('schema_version') != 1:
        raise ValueError('Unsupported source/schema')
    if summary.get('saved_records') != len(frames):
        raise ValueError('Summary frame count mismatch')
    cap_reached = summary.get('status') == 'error' and summary.get('detail') == CAP_REASON
    if summary.get('status') != 'complete' and not cap_reached:
        raise ValueError('Unrecognized recording error: ' + str(summary.get('detail')))

    iq_hash = hashlib.sha256()
    for f in frames:
        if f.get('subcarrier_count') != 64:
            raise ValueError('v3 supports 64-subcarrier data only')
        for key in ('i', 'q', 'amplitude', 'phase_rad'):
            vals = f.get(key)
            if not isinstance(vals, list) or len(vals) != 64 or not all(math.isfinite(v) for v in vals):
                raise ValueError('Invalid array: ' + key)
        if any(type(v) is not int or not -128 <= v <= 127 for key in ('i', 'q') for v in f[key]):
            raise ValueError('I/Q must be int8 values')
        raw = base64.b64decode(f['raw_csi_v8_base64'], validate=True)
        if (len(raw) != 192 or struct.unpack_from('<H', raw, 0)[0] != 0x4353
                or raw[2] != 8 or raw[3] != 64
                or struct.unpack_from('<H', raw, 10)[0] != 64
                or struct.unpack_from('<H', raw, 12)[0] != 128):
            raise ValueError('Invalid CSI V8 raw record')
        iq_hash.update(raw)
        payload = np.frombuffer(raw[64:], dtype=np.int8)
        if payload[::2].tolist() != f['q'] or payload[1::2].tolist() != f['i']:
            raise ValueError('Raw bytes disagree with parsed I/Q')
        if struct.unpack_from('<Q', raw, 22)[0] != int(f['device_capture_us']):
            raise ValueError('Raw timestamp mismatch')
        if not np.allclose(np.hypot(f['i'], f['q']), f['amplitude'], atol=1e-10, rtol=1e-10):
            raise ValueError('Amplitude does not agree with I/Q')
        if not np.allclose(np.arctan2(f['q'], f['i']), f['phase_rad'], atol=1e-10, rtol=1e-10):
            raise ValueError('Phase does not agree with I/Q')

    ticks = [int(f['device_capture_us']) for f in frames]
    t = np.array([(v-ticks[0])/1e6 for v in ticks])
    seq = np.array([int(f['sequence']) for f in frames], dtype=np.int64)
    if np.any(np.diff(t) <= 0) or np.any(np.diff(seq) <= 0):
        raise ValueError('Nonincreasing capture time or sequence')
    a = np.hypot(np.array([f['i'] for f in frames], dtype=float),
                 np.array([f['q'] for f in frames], dtype=float))
    host = np.array([f['browser_received_epoch_ms'] for f in frames], dtype=float)
    if not np.isfinite(host).all() or np.any(np.diff(host) < 0):
        raise ValueError('Invalid/backward host time')
    audit = dict(frames=len(frames), duration_s=float(t[-1]),
                 sampling_rate_hz=float((len(frames)-1)/t[-1]),
                 missing_sequences=int(np.sum(np.diff(seq)-1)),
                 max_interval_ms=float(np.max(np.diff(t))*1000),
                 status=summary['status'], cap_prefix_accepted=cap_reached,
                 raw_sha256=iq_hash.hexdigest(), session_id=meta['session_id'],
                 room=meta.get('room'), device_field=meta.get('device'),
                 original_label=meta.get('initial_label'),
                 first_host_ms=float(host[0]), last_host_ms=float(host[-1]))
    return meta, t, seq, a, audit

def features(a):
    # Same features as v2: no tuning or global fitted normalization.
    relative = a / np.maximum(a.mean(axis=0), 1.0)
    delta = np.diff(relative, axis=0)
    return np.concatenate([relative.std(axis=0), np.mean(np.abs(delta), axis=0),
                           np.ptp(relative, axis=0), delta.std(axis=0)])

def make_windows(t, seq, a, start_s=1.0, end_trim_s=1.0):
    if start_s < 0 or end_trim_s < 0:
        raise ValueError('Trim times must be nonnegative')
    accepted, rejected = [], []
    for start in np.arange(start_s, t[-1]-end_trim_s-WINDOW_S+1e-8, WINDOW_S):
        ix = np.flatnonzero((t >= start) & (t < start+WINDOW_S))
        problems = []
        if not 180 <= len(ix) <= 220:
            problems.append('frame_count')
        if len(ix) < 2:
            problems.append('too_few_frames')
        else:
            if t[ix[-1]]-t[ix[0]] < 1.9:
                problems.append('time_coverage')
            if np.max(np.diff(t[ix])) > .05:
                problems.append('time_gap')
            if np.any(np.diff(seq[ix]) != 1):
                problems.append('sequence_gap')
        item = dict(start_s=float(start), end_s=float(start+WINDOW_S), frames=len(ix))
        if problems:
            rejected.append(dict(**item, reason=';'.join(problems)))
        else:
            accepted.append(dict(**item, x=features(a[ix])))
    return accepted, rejected
