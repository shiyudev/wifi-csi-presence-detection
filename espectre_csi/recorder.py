"""带标签的 CSI 采集会话。

每个会话保存为一个目录：
    data/<exp_id>/
        meta.json        实验元数据（标签、描述、设备信息、PPS 等）
        csi.npz          ESPectre 兼容数据：csi_data int8 [N, SC*2] 及时间/序列数组
        csi_raw.bin      原始帧字节（可选，用于事后复核解析）
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from .protocol import (
    CSIPacket,
    CSIStreamClient,
    DeviceControl,
    TrafficGenerator,
    iq_to_amplitude_matrix,
)

# 建议使用的标签词汇表（可自由扩展，训练时通过 label_map 归并）
SUGGESTED_LABELS = [
    "empty",          # 房间无人、无干扰源
    "static",         # 有人在房间内静止（坐着/站着不动）
    "walk",           # 走动
    "typing",         # 敲键盘
    "page_turning",   # 翻书
    "fan",            # 无人，风扇开
    "robot_vacuum",   # 无人，扫地机器人
]


@dataclass
class RecordConfig:
    """一次采集会话的配置。"""

    label: str
    description: str = ""
    duration_s: float = 60.0
    traffic_pps: float = 100.0
    save_raw: bool = False
    extra: dict = field(default_factory=dict)


class SessionRecorder:
    """连接设备，切换 external 流量模式，采集指定时长并保存。"""

    def __init__(self, host: str, port: int = 62587, out_dir: str | Path = "data"):
        self.host = host
        self.port = port
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.control = DeviceControl(host, port)
        self.client = CSIStreamClient(host, port)
        self.traffic = TrafficGenerator(host, pps=100.0)
        self._stop_flag = False

    def request_stop(self):
        """提前结束当前采集（线程安全，网页"停止采集"用）。"""
        self._stop_flag = True

    def record(self, cfg: RecordConfig,
               on_progress: Optional[Callable[[float, int, float], None]] = None) -> Path:
        """采集一段带标签的数据，返回会话目录。

        on_progress(elapsed_s, packets, pps) 每 0.5s 回调一次。
        """
        # 1) 健康检查 + 等待检测器就绪
        # 外部流量模式的 CSI 流不依赖设备端运动检测器就绪，短暂等待即可
        health = self.control.health()
        dev = self.control.device()
        self.control.wait_ready(timeout=5.0)
        sensing_before = self.control.sensing()
        prev_mode = sensing_before.get("traffic_generator_mode", "ping")

        # 2) 切换到 external 流量模式
        # 上一个 CSI 会话尚未完全释放时设备会返回 409，重试几次
        for attempt in range(5):
            try:
                self.control.set_sensing(traffic_generator_mode="external")
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1.0)
        time.sleep(0.5)

        exp_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cfg.label}"
        session_dir = self.out_dir / exp_id
        session_dir.mkdir(parents=True)

        iq_rows: List[np.ndarray] = []
        times: List[float] = []
        ticks: List[int] = []
        seqs: List[int] = []
        raw_frames: List[bytes] = []
        raw_file = None

        self.traffic.pps = cfg.traffic_pps
        self.traffic.start()
        t0 = time.time()
        last_report = 0.0
        interrupted = False
        self._stop_flag = False
        try:
            for packet in self.client.packets():
                iq_rows.append(packet.iq_raw)
                times.append(packet.timestamp)
                ticks.append(packet.device_ticks_us or 0)
                seqs.append(packet.stream_sequence)
                elapsed = time.time() - t0
                if cfg.save_raw:
                    if raw_file is None:
                        raw_file = open(session_dir / "csi_raw.bin", "wb")
                    # 原始帧已在流客户端中拆包，这里保存 IQ+时间戳即可复核
                    raw_file.write(packet.iq_raw.tobytes())
                if on_progress and elapsed - last_report >= 0.5:
                    last_report = elapsed
                    on_progress(elapsed, len(iq_rows), self.client.observed_pps)
                if elapsed >= cfg.duration_s or self._stop_flag:
                    interrupted = self._stop_flag
                    break
        except KeyboardInterrupt:
            interrupted = True
        finally:
            self.traffic.stop()
            if raw_file:
                raw_file.close()
            # 3) 恢复原流量模式，避免设备停留在 external 后无人发包
            try:
                self.control.set_sensing(traffic_generator_mode=prev_mode)
            except Exception:
                pass

        if not iq_rows:
            raise RuntimeError("未收到任何 CSI 包：请检查设备 IP、网络连通性与端口")

        csi_data = np.stack(iq_rows)                       # int8 [N, SC*2]
        stats = dict(self.client.stats)
        meta = {
            "exp_id": exp_id,
            "label": cfg.label,
            "description": cfg.description,
            "started_at": datetime.fromtimestamp(times[0]).isoformat(),
            "duration_s": round(times[-1] - times[0], 3),
            "packets": int(len(iq_rows)),
            "traffic_pps": cfg.traffic_pps,
            "device": {k: dev.get(k) for k in ("chip", "model", "label", "version")},
            "health": {k: health.get(k) for k in ("state", "uptime_ms")},
            "stream": {
                "session_id": self.client.session_id.hex(),
                "frames": stats.get("frames", 0),
                "parse_errors": stats.get("parse_errors", 0),
                "stream_gaps": stats.get("stream_gaps", 0),
                "interrupted": interrupted,
            },
            "extra": cfg.extra,
        }
        (session_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        mean_pps = len(times) / max(1e-9, times[-1] - times[0])
        np.savez_compressed(
            session_dir / "csi.npz",
            csi_data=csi_data,
            timestamp=np.asarray(times, dtype=np.float64),
            device_ticks_us=np.asarray(ticks, dtype=np.int64),
            stream_sequence=np.asarray(seqs, dtype=np.int64),
            # ESPectre 官方字段命名，便于互通
            label=cfg.label,
            mean_pps=mean_pps,
        )
        print(f"[recorder] 已保存 {exp_id}: {len(iq_rows)} 包, "
              f"平均 {mean_pps:.1f} pps, 丢帧 {stats.get('stream_gaps', 0)}")
        return session_dir


def load_session(path: str | Path) -> dict:
    """读取一个会话目录，返回 csi(幅度矩阵)/iq/时间/标签。"""
    p = Path(path)
    npz_path = p / "csi.npz"
    if not npz_path.exists():
        npz_path = p
    with np.load(npz_path, allow_pickle=False) as z:
        iq = z["csi_data"]
        times = z["timestamp"]
        label = str(z["label"]) if "label" in z.files else json.loads(
            (p / "meta.json").read_text(encoding="utf-8"))["label"]
    meta = {}
    meta_path = p / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "path": p, "label": label, "iq": iq, "times": times,
        "amplitudes": iq_to_amplitude_matrix(iq), "meta": meta,
    }
