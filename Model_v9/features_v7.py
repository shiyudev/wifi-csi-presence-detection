"""Within-two-second common-carrier features; no label, filename, or global fit."""
import numpy as np

from data_v6 import read_archive as read_base_archive, window_rows as base_windows

FEATURE_NAMES = ('std', 'mean_abs_diff', 'median_abs_diff', 'p90_abs_diff',
                 'iqr', 'p90_p10', 'p95_p05', 'half_mean_shift',
                 'lag1_correlation', 'lag10_correlation', 'power_05_3', 'power_3_10')


def median_five(x):
    """Center within the already observed window; never reads outside it."""
    return np.median(np.lib.stride_tricks.sliding_window_view(np.pad(x, (2, 2), mode='edge'), 5), axis=-1)


def describe(x, sampling_hz):
    difference = np.abs(np.diff(x))
    q05, q10, q25, q75, q90, q95 = np.quantile(x, [.05, .1, .25, .75, .9, .95])
    values = [x.std(), difference.mean(), np.median(difference), np.quantile(difference, .9),
              q75-q25, q90-q10, q95-q05, abs(x[len(x)//2:].mean()-x[:len(x)//2].mean())]
    for lag in (1, 10):
        left, right = x[:-lag]-x[:-lag].mean(), x[lag:]-x[lag:].mean()
        norm = np.linalg.norm(left)*np.linalg.norm(right)
        values.append(float(left@right/norm) if norm > 1e-12 else 0.)
    power = np.abs(np.fft.rfft((x-x.mean())*np.hanning(len(x))))**2
    frequency = np.fft.rfftfreq(len(x), d=1/sampling_hz)
    total = power[frequency >= .5].sum()
    for low, high in ((.5, 3.), (3., 10.)):
        energy = power[(frequency >= low)&(frequency < high)].sum()
        values.append(float(energy/total) if total > 1e-12 else 0.)
    output = np.array(values, float)
    if len(output) != len(FEATURE_NAMES) or not np.isfinite(output).all():
        raise ValueError('Nonfinite common-carrier features')
    return output


def common_features(t, amplitude):
    if len(t) < 2 or amplitude.shape != (len(t), 64):
        raise ValueError('Expected at least two frames with 64 carriers')
    active = amplitude.mean(axis=0) > 1.
    if not active.any():
        return np.zeros(12), np.zeros(12)
    selected = amplitude[:, active]
    relative = selected/np.maximum(np.median(selected, axis=0), 1.) - 1.
    common = np.median(relative, axis=1)
    grid = np.linspace(t[0], t[-1], 200)
    common = np.interp(grid, t, common)
    rate = 199/(grid[-1]-grid[0])
    return describe(common, rate), describe(median_five(common), rate)


def add_features(rows, t, a):
    for row in rows:
        if row['quality'] != 'accepted':
            row.update(common=None, common_median=None)
            continue
        mask = (t >= row['start_s']) & (t < row['end_s'])
        common, filtered = common_features(t[mask], a[mask])
        row.update(common=common, common_median=filtered)
    return rows


def window_rows(t, seq, a, item):
    return add_features(base_windows(t, seq, a, item), t, a)


def read_archive(archive, manifest):
    config, raw, rows = read_base_archive(archive, manifest)
    for name, record in raw.items():
        add_features([r for r in rows if r['file'] == name], record['t'], record['a'])
    return config, raw, rows
