"""实时 CSI 可视化：原始子载波幅度曲线 + 偏差瀑布图。

画法与官方 csi-visualizer 对齐：
- 上面板画【原始幅度】（int8 IQ 的模，典型值 40~90，平缓），
  不是归一化值；Y 轴范围按滚动 30 秒的 1%~99% 分位数固定，
  避免每帧自动缩放导致的"一直在波动"的错觉。
- 曲线自带 0.2s 滑动平均（可关），人走近/走动时能看到明显台阶或起伏。
- 下面板瀑布图画每子载波相对均值的偏差，用于看哪些子载波对动作敏感。

用法:
    python scripts/live_view.py --host 192.168.1.50
    python scripts/live_view.py --host 192.168.1.50 --sc 3,11,27,43
    python scripts/live_view.py --host 192.168.1.50 --no-smooth
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path

import numpy as np

from .protocol import CSIStreamClient, DeviceControl, TrafficGenerator

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    # Windows 默认字体不含中文，标题会显示为方块
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
except Exception:  # pragma: no cover
    matplotlib = None


def smooth(x: np.ndarray, k: int) -> np.ndarray:
    """滑动平均，边缘用复制填充（避免 convolve 'same' 的零填充下坠伪影）。"""
    if k <= 1:
        return x
    kernel = np.ones(k) / k
    if x.ndim == 1:
        xp = np.pad(x, k // 2, mode="edge")
        return np.convolve(xp, kernel, mode="valid")[: len(x)]
    return np.apply_along_axis(lambda c: smooth(c, k), 0, x)


class LiveViewer:
    def __init__(self, host: str, port: int = 62587,
                 duration_s: float = 10.0, traffic_pps: float = 100.0,
                 subcarriers=None, smooth_s: float = 0.2,
                 waterfall: bool = True, snapshot_dir=None,
                 snapshot_interval_s: float = 5.0):
        if matplotlib is None:
            raise RuntimeError("需要 matplotlib 才能实时显示")
        self.host = host
        self.port = port
        self.duration_s = duration_s
        self.traffic = TrafficGenerator(host, pps=traffic_pps)
        self.control = DeviceControl(host, port)
        self.client = CSIStreamClient(host, port)
        self.subcarriers = subcarriers      # None = 自动挑 8 个
        self.smooth_n = max(1, int(smooth_s * traffic_pps))
        self.waterfall = waterfall
        self.history = deque(maxlen=4000)   # (t, amp[SC])
        self.snapshot_dir = snapshot_dir
        self.snapshot_interval_s = snapshot_interval_s
        self._last_snap = 0.0

    # ------------------------------------------------------------------
    def run(self):
        self.control.wait_ready(timeout=5.0)
        prev_mode = self.control.sensing().get("traffic_generator_mode", "ping")
        self.control.set_sensing(traffic_generator_mode="external")
        self.traffic.start()

        show = self.subcarriers
        lines = None
        last_ylim_t = 0.0
        last_draw_t = 0.0

        fig, axes = plt.subplots(2 if self.waterfall else 1, 1,
                                 figsize=(11, 7), sharex=True)
        axes = np.atleast_1d(axes)
        ax1 = axes[0]
        ax1.set_ylabel("原始幅度 (raw amplitude)")
        ax1.grid(alpha=0.3)
        ax1.set_title(f"子载波原始幅度曲线（滚动 {self.duration_s:.0f} 秒）"
                      f"—— 人走近/走动时曲线抬升或起伏")
        if self.waterfall:
            ax2 = axes[1]
            img = ax2.imshow(np.zeros((64, 1)), aspect="auto", origin="lower",
                             cmap="viridis", vmin=-3, vmax=15)
            ax2.set_ylabel("子载波")
            ax2.set_xlabel("时间 (s)")
        plt.ion()
        plt.show()

        try:
            for pkt in self.client.packets(retry=True):
                self.history.append((pkt.timestamp, pkt.amplitudes))
                now = pkt.timestamp
                if now - last_draw_t < 0.08:      # ~12 帧/秒足够流畅
                    continue
                last_draw_t = now

                recent = [(t, a) for t, a in self.history
                          if now - t <= self.duration_s]
                if len(recent) < 10:
                    continue
                times = np.array([t for t, _ in recent])
                amps = np.stack([a for _, a in recent]).astype(np.float32)
                rel_t = times - times[0]

                if show is None:
                    # 按窗口内标准差挑变化最大的 8 个子载波
                    var = amps.std(axis=0)
                    show = sorted(np.argsort(var)[-8:])
                    show = [int(s) for s in show]
                data = smooth(amps[:, show], self.smooth_n)

                if lines is None:
                    cmap = plt.get_cmap("tab10")
                    lines = [ax1.plot(rel_t, data[:, i], lw=1.0,
                                      color=cmap(i), label=f"SC {s}")[0]
                             for i, s in enumerate(show)]
                    ax1.legend(loc="upper left", fontsize=8, ncol=4)
                else:
                    for i, ln in enumerate(lines):
                        ln.set_data(rel_t, data[:, i])

                # Y 轴范围：每 2 秒用 1%~99% 分位数固定一次（不逐帧缩放）
                if now - last_ylim_t > 2.0:
                    last_ylim_t = now
                    lo, hi = np.percentile(data, [1, 99])
                    pad = max(2.0, (hi - lo) * 0.15)
                    ax1.set_ylim(lo - pad, hi + pad)
                    ax1.set_xlim(0, self.duration_s)

                if self.waterfall:
                    dev = amps - amps.mean(axis=0, keepdims=True)
                    img.set_data(dev.T)
                    img.set_extent([rel_t[0], rel_t[-1], 0, amps.shape[1]])
                    ax2.set_title("瀑布图：偏离窗口均值的幅度（亮 = 该子载波正在变化）")
                fig.canvas.draw_idle()
                plt.pause(0.001)

                # 定期保存截图（保留最近 10 张），便于回看与交付
                if self.snapshot_dir is not None:
                    if now - self._last_snap >= self.snapshot_interval_s:
                        self._last_snap = now
                        p = Path(self.snapshot_dir) / \
                            f"live_{time.strftime('%H%M%S')}.png"
                        fig.savefig(p, dpi=110)
                        snaps = sorted(Path(self.snapshot_dir).glob("live_*.png"))
                        for old in snaps[:-10]:
                            old.unlink(missing_ok=True)
        except KeyboardInterrupt:
            pass
        finally:
            self.traffic.stop()
            try:
                self.control.set_sensing(traffic_generator_mode=prev_mode)
            except Exception:
                pass
            plt.ioff()
            plt.close(fig)
