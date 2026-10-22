"""滑动窗口特征提取。

思路：把连续 CSI 流切成固定时长窗口（默认 2 秒），
每个窗口提取对"人是否在动"敏感、对绝对信号强度不敏感的特征。

关键设计：
- 用每个子载波幅度自身的窗口内归一化（减均值除标准差），
  消除设备、距离、温度带来的直流漂移 → 跨环境更稳。
- 方差、相邻包差分、频谱能量占比等特征在 ESPectre
  与学术文献（Widar3.0、RT-Fall 等）中均被验证有效。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class WindowConfig:
    window_s: float = 2.0     # 窗口时长
    step_s: float = 0.5       # 滑动步长（实时推理的输出周期）
    min_pps: float = 20.0     # 低于该速率的窗口丢弃（数据质量线）
    smooth_s: float = 0.1     # 包间平滑窗口（按时间中值滤波）


def cut_windows(times: np.ndarray, amp: np.ndarray,
                cfg: WindowConfig) -> List[Tuple[float, np.ndarray]]:
    """按时间切成 [窗口起始时间, 幅度矩阵 [T, SC]] 列表。"""
    if len(times) < 2:
        return []
    t0, t1 = times[0], times[-1]
    windows = []
    start = t0
    while start + cfg.window_s <= t1:
        mask = (times >= start) & (times < start + cfg.window_s)
        seg = amp[mask]
        if len(seg) >= cfg.min_pps * cfg.window_s * 0.5:
            windows.append((float(start), seg))
        start += cfg.step_s
    return windows


def features_for_window(amp: np.ndarray) -> np.ndarray:
    """从一个 [T, SC] 幅度窗口提取特征向量。

    特征（全部对幅度做窗口内归一化后计算）：
      f1  每子载波归一化方差（SC 维）
      f2  归一化方差统计量: max/std/mean (3 维)
      f3  相邻包差分的 RMS（SC 维）——反映"变化速度"
      f4  差分 RMS 统计量: max/mean (2 维)
      f5  跨子载波相关性均值——人移动引起的相关结构变化 (1 维)
    """
    if amp.shape[0] < 4:
        return np.zeros(0, dtype=np.float32)
    # 窗口内归一化: 每个子载波减均值除标准差
    mu = amp.mean(axis=0, keepdims=True)
    sd = amp.std(axis=0, keepdims=True) + 1e-6
    x = (amp - mu) / sd

    f1 = x.var(axis=0).astype(np.float32)                    # [SC]
    f2 = np.array([f1.max(), f1.std(), f1.mean()], np.float32)

    diff = np.diff(x, axis=0)
    f3 = np.sqrt((diff ** 2).mean(axis=0)).astype(np.float32)  # [SC]
    f4 = np.array([f3.max(), f3.mean()], np.float32)

    # 真实设备常有恒定子载波（标准差为 0），直接 corrcoef 会产生
    # 除零警告与 NaN；只对非常数列求相关，其余填 0
    sc = x.shape[1]
    ok = x.std(axis=0) > 1e-9
    corr = np.zeros((sc, sc), dtype=np.float32)
    if ok.sum() > 1:
        c = np.corrcoef(x[:, ok], rowvar=False)
        corr[np.ix_(ok, ok)] = c
    if sc > 1:
        off = corr[~np.eye(sc, dtype=bool)]
        f5 = np.array([np.nanmean(off)], np.float32)
    else:
        f5 = np.zeros(1, np.float32)

    return np.concatenate([f1, f2, f3, f4, f5]).astype(np.float32)


def feature_names(n_sc: int) -> List[str]:
    names = [f"var_sc{i}" for i in range(n_sc)]
    names += ["var_max", "var_std", "var_mean"]
    names += [f"diff_rms_sc{i}" for i in range(n_sc)]
    names += ["diff_rms_max", "diff_rms_mean"]
    names += ["cross_corr_mean"]
    return names


def motion_ratio_feature(amp: np.ndarray, baseline_std: np.ndarray) -> float:
    """轻量实时指标：窗口内方差超出空房间基线的比例（0~1+）。

    baseline_std 为空房间标定得到的每子载波标准差 [SC]。
    """
    if baseline_std is None or amp.shape[0] < 4:
        return 0.0
    mu = amp.mean(axis=0, keepdims=True)
    x = (amp - mu) / (baseline_std.reshape(1, -1) + 1e-6)
    var = x.var(axis=0)
    return float((var > 3.0).mean())


FEATURE_GROUP_SIZES = lambda n_sc: (n_sc, 3, n_sc, 2, 1)
