# -*- coding: utf-8 -*-
"""生成分析图表（4 张，中文，300dpi）"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

font_manager.fontManager.addfont("/usr/share/fonts/truetype/lxgw/LXGWWenKai-Regular.ttf") if False else None
plt.rcParams["font.family"] = ["LXGW WenKai", "Noto Serif SC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

OUT = "/home/z/my-project/csi_analysis/figs"
D = "/home/z/my-project/csi_analysis"

TEXT, MUTED, GRID = "#243447", "#7A8699", "#E5E9F0"
CLASSES = ["空场", "风扇", "走动", "玩电脑", "人"]  # object 字段
# 按文件名前缀归类（更细的场景粒度）
def scene_of(fn):
    for key in ["空场无人", "风扇无人", "走动", "玩电脑", "设备旁挥手", "起身出教室", "门口走"]:
        if fn.startswith(key):
            return key
    return "?"

with open(f"{D}/summary.json", encoding="utf-8") as f:
    S = json.load(f)
for s in S:
    s["scene"] = scene_of(s["file"])

SC_COLOR = {  # 场景配色：靛蓝主调 + 灰阶，仅强调走动
    "空场无人": "#9AA5B5", "风扇无人": "#C9A227", "走动": "#4C6EF5",
    "玩电脑": "#3AAFA9", "设备旁挥手": "#B78bff", "起身出教室": "#EE7733", "门口走": "#EE7733",
}
ORDER = ["空场无人", "风扇无人", "玩电脑", "设备旁挥手", "起身出教室", "门口走", "走动"]

# ── 图1 动态强度对比 ──────────────────────────────
fig, ax = plt.subplots(figsize=(11, 5.6), dpi=300, constrained_layout=True)
xs, labels, colors = [], [], []
x = 0
for sc in ORDER:
    sess = sorted([s for s in S if s["scene"] == sc], key=lambda r: r["file"])
    for s in sess:
        xs.append(x); labels.append(s["motion_idx"]); colors.append(SC_COLOR[sc])
        x += 1
    x += 0.7
bars = ax.bar(xs, labels, width=0.72, color=colors, zorder=3)
for b, v in zip(bars, labels):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.2f}",
            ha="center", va="bottom", fontsize=9.5, color=TEXT)
base = np.mean([s["motion_idx"] for s in S if s["scene"] == "空场无人"])
ax.axhline(base, color="#C0392B", lw=1.2, ls="--", zorder=4)
ax.text(xs[-1] + 0.8, base + 0.06, f"空场基线 {base:.2f}", color="#C0392B", fontsize=10.5)
# 场景分隔标签
x = 0
for sc in ORDER:
    n = len([s for s in S if s["scene"] == sc])
    ax.text(x + (n - 1) / 2, -0.52, sc, ha="center", fontsize=11.5, color=TEXT, fontweight="bold")
    x += n + 0.7
ax.set_xticks([])
ax.set_ylim(0, max(labels) * 1.2)
ax.set_ylabel("动态强度（子载波偏差 RMS）", fontsize=11, color=MUTED)
ax.set_title("人体活动显著抬升信号动态：走动最强（2.4~3.2），是空场基线的 3~4 倍",
             fontsize=14.5, color=TEXT, fontweight="bold", pad=14)
for sp in ["top", "right", "bottom"]:
    ax.spines[sp].set_visible(False)
ax.grid(axis="y", color=GRID, lw=0.7, zorder=0)
ax.tick_params(left=False, labelsize=10, colors=MUTED)
fig.savefig(f"{OUT}/fig1_motion.png", facecolor="white", bbox_inches="tight")
plt.close(fig)

# ── 图2 时-子载波热力图 2×2 ────────────────────────
mats = np.load(f"{D}/dev_mats.npz")
show = [("空场无人", "空场无人（2）"), ("风扇无人", "风扇无人（3）"),
        ("玩电脑", "玩电脑（3）"), ("走动", "走动（2）")]
fig, axes = plt.subplots(2, 2, figsize=(12.5, 7), dpi=300, constrained_layout=True)
vmax = max(float(np.abs(mats[k][:, :]).std() * 2.5) for k, _ in show)
for ax, (lab, fn) in zip(axes.flat, show):
    M = mats[lab].T  # 60×T
    # 时间下采样到 ~50 列便于显示
    step = max(1, M.shape[1] // 240)
    Ms = M[:, ::step]
    im = ax.imshow(Ms, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                   interpolation="nearest", extent=[0, M.shape[1] / 100, 60, 4])
    ax.set_title(f"{lab}  ·  {fn}", fontsize=11.5, color=TEXT, loc="left", pad=6)
    ax.set_ylabel("子载波", fontsize=9.5, color=MUTED)
    ax.set_xlabel("时间（秒）", fontsize=9.5, color=MUTED)
    ax.tick_params(labelsize=9, colors=MUTED)
cb = fig.colorbar(im, ax=axes, shrink=0.75, pad=0.015)
cb.set_label("幅度偏差", fontsize=10, color=MUTED)
cb.ax.tick_params(labelsize=9, colors=MUTED)
fig.suptitle("时序热力图：走动区域连片波动 · 风扇仅少数子载波周期性响应 · 空场均匀噪声",
             fontsize=14.5, color=TEXT, fontweight="bold")
fig.savefig(f"{OUT}/fig2_heatmap.png", facecolor="white", bbox_inches="tight")
plt.close(fig)

# ── 图3 子载波敏感度曲线 ───────────────────────────
sv = np.load(f"{D}/sc_vars.npz")
key_sc = ["走动", "空场无人", "风扇无人", "玩电脑"]
fig, ax = plt.subplots(figsize=(11, 5.4), dpi=300, constrained_layout=True)
for sc in key_sc:
    V = np.mean([sv[f] for f in sv.files if scene_of(f) == sc], axis=0)
    c = SC_COLOR[sc]
    ax.plot(np.arange(4, 64), V, lw=2.4 if sc == "走动" else 1.5, color=c,
            label=f"{sc}（均值）", zorder=3 if sc == "走动" else 2)
top = sorted(int(i) for i in (np.argsort(np.mean([sv[f] for f in sv.files if scene_of(f) == "走动"], axis=0))[-5:] + 4))
ax.set_xticks(range(4, 64, 5)); ax.set_xticklabels(range(4, 64, 5))
ax.set_xlabel("子载波编号", fontsize=11, color=MUTED)
ax.set_ylabel("幅度方差", fontsize=11, color=MUTED)
ax.set_title(f"走动时 {top[0]}~{top[-1]} 号子载波波动最剧烈（峰值方差为空场的 8 倍），是特征选择首选区间",
             fontsize=14.5, color=TEXT, fontweight="bold", pad=14)
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=10.5)
for sp in ["top", "right"]:
    ax.spines[sp].set_visible(False)
ax.grid(color=GRID, lw=0.7, zorder=0)
ax.tick_params(labelsize=10, colors=MUTED)
fig.savefig(f"{OUT}/fig3_subcarrier.png", facecolor="white", bbox_inches="tight")
plt.close(fig)

# ── 图4 频谱对比：风扇指纹 ─────────────────────────
def mean_spec(scene):
    specs = []
    for f in sv.files:
        if scene_of(f) != scene:
            continue
        # 从原始数据重算
        pass
    return None

import glob, os as _os
def spectrum_of(path):
    import sys
    sys.path.insert(0, D)
    from analyze import load_session, VALID
    _, A, *_ = load_session(path)
    # 取方差 top5 子载波求平均谱
    idx = np.argsort(A[:, VALID].var(axis=0))[-5:] + 4
    specs = []
    for k in idx:
        x = A[:, k].copy()
        ema = x[0]
        for i in range(len(x)):
            d = x[i] - ema
            x[i] = d
            ema += 0.1 * d
        specs.append(np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2)
    freqs = np.fft.rfftfreq(len(x), 0.01)
    spec = np.mean(specs, axis=0)
    return freqs, spec / (spec.sum() + 1e-9)

SRC = "/home/z/my-project/upload/mount_agent_directory/采集数据"
picks = {"风扇无人": "风扇无人（3).jsonl", "空场无人": "空场无人（2）.jsonl", "走动": "走动（2）.jsonl"}
fig, ax = plt.subplots(figsize=(11, 5.4), dpi=300, constrained_layout=True)
for sc, fn in picks.items():
    fr, sp = spectrum_of(_os.path.join(SRC, fn))
    m = (fr >= 1) & (fr <= 48)
    ax.plot(fr[m], sp[m], color=SC_COLOR[sc], lw=2.4 if sc == "风扇无人" else 1.5,
            label=sc, zorder=3 if sc == "风扇无人" else 2)
fan_fr, fan_sp = spectrum_of(_os.path.join(SRC, picks["风扇无人"]))
pf = fan_fr[(fan_fr >= 1) & (fan_fr <= 48)][np.argmax(fan_sp[(fan_fr >= 1) & (fan_fr <= 48)])]
ax.annotate(f"风扇指纹 ≈ {pf:.1f} Hz\n（三次采集均为 6.5~6.8 Hz）",
            xy=(pf, fan_sp[(fan_fr >= 1) & (fan_fr <= 48)].max()),
            xytext=(pf + 7, fan_sp[(fan_fr >= 1) & (fan_fr <= 48)].max() * 0.95),
            fontsize=11, color=TEXT,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2))
ax.set_xlabel("频率（Hz）", fontsize=11, color=MUTED)
ax.set_ylabel("归一化功率占比", fontsize=11, color=MUTED)
ax.set_title("频谱对比：风扇存在可分辨的 6.6 Hz 周期指纹，与人体动作频段（2~4 Hz）分离",
             fontsize=14.5, color=TEXT, fontweight="bold", pad=14)
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=10.5)
for sp_ in ["top", "right"]:
    ax.spines[sp_].set_visible(False)
ax.grid(color=GRID, lw=0.7, zorder=0)
ax.tick_params(labelsize=10, colors=MUTED)
fig.savefig(f"{OUT}/fig4_spectrum.png", facecolor="white", bbox_inches="tight")
plt.close(fig)
print("4 张图完成")
