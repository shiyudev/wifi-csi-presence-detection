"""实时检测器：滑动窗口推理 + 预测日志。

运行后每个 step_s（默认 0.5 秒）输出一次判断：
    有人移动 / 无人（无移动）
并把 (时间戳, 判断, 分数, pps, 丢包) 追加写入 outputs/predictions_*.csv，
同时保存一份与会话对应的 JSONL（便于事后评测）。
"""

from __future__ import annotations

import csv
import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from .features import WindowConfig, features_for_window, motion_ratio_feature
from .model import load_model
from .protocol import CSIStreamClient, DeviceControl, TrafficGenerator


class RealtimeDetector:
    def __init__(self, host: str, model_path: str | Path,
                 port: int = 62587, out_dir: str | Path = "outputs",
                 window_cfg: Optional[WindowConfig] = None,
                 score_threshold: float = 0.5,
                 hysteresis: int = 2):
        self.host = host
        self.port = port
        self.window_cfg = window_cfg or WindowConfig()
        self.score_threshold = score_threshold
        self.hysteresis = hysteresis   # 连续 N 次一致才切换状态（时间连续性判别）
        self.model, self.meta = load_model(model_path)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.control = DeviceControl(host, port)
        self.client = CSIStreamClient(host, port)
        self.traffic = TrafficGenerator(host, pps=100.0)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = self.out_dir / f"predictions_{stamp}.csv"
        self.jsonl_path = self.out_dir / f"predictions_{stamp}.jsonl"
        self._csv_file = None
        self._csv_writer = None

        # 滑动缓冲
        self._times: deque = deque()
        self._amps: deque = deque()
        self._state = 0            # 0=idle 1=motion
        self._pending = 0          # 与当前状态相反的连续计数
        self._last_score = 0.0
        self.state_since: Optional[float] = None
        self.last_prediction: Optional[dict] = None   # 供外部(如 WebUI)读取
        self.on_prediction = None                     # 回调: f(row: dict)
        self._stop_flag = False

    def stop(self):
        """请求停止 run() 循环（线程安全）。"""
        self._stop_flag = True

    def _log(self, row: dict):
        if self._csv_writer is None:
            self._csv_file = open(self.csv_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.DictWriter(
                self._csv_file, fieldnames=["timestamp", "state", "score", "pps",
                                            "stream_gaps", "rssi_dbm"])
            self._csv_writer.writeheader()
        self._csv_writer.writerow({k: row.get(k, "") for k in self._csv_writer.fieldnames})
        self._csv_file.flush()
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _update_state(self, score: float) -> int:
        raw = 1 if score >= self.score_threshold else 0
        if raw == self._state:
            self._pending = 0
        else:
            self._pending += 1
            if self._pending >= self.hysteresis:
                self._state = raw
                self._pending = 0
                self.state_since = time.time()
        return self._state

    def run(self, duration_s: float = 0.0):
        """持续检测；duration_s<=0 表示直到 Ctrl+C。"""
        # 校验模型：必须是两类模型，否则 predict_proba 没有意义
        classes = getattr(self.model, "classes_", None)
        if classes is not None and len(classes) < 2:
            raise RuntimeError(
                f"模型只学到一个类别 {list(classes)}（训练数据缺少 idle 或 motion "
                "样本），无法用于检测；请补采另一类数据后重新训练")
        print(f"[detector] 模型验证准确率 {self.meta.get('val_accuracy')}, "
              f"窗口 {self.window_cfg.window_s}s / 步长 {self.window_cfg.step_s}s")
        self.control.wait_ready(timeout=5.0)
        prev_mode = self.control.sensing().get("traffic_generator_mode", "ping")
        self.control.set_sensing(traffic_generator_mode="external")
        self.traffic.start()

        t0 = time.time()
        last_eval = 0.0
        try:
            for pkt in self.client.packets():
                self._times.append(pkt.timestamp)
                self._amps.append(pkt.amplitudes)
                # 丢弃窗口外的旧数据
                while self._times and self._times[0] < pkt.timestamp - self.window_cfg.window_s:
                    self._times.popleft(); self._amps.popleft()

                now = time.time()
                if now - last_eval >= self.window_cfg.step_s:
                    last_eval = now
                    if len(self._times) >= self.window_cfg.window_s * 20:
                        times = np.asarray(self._times)
                        amps = np.stack(self._amps)
                        mask = times >= pkt.timestamp - self.window_cfg.window_s
                        window = amps[mask]
                        feat = features_for_window(window)
                        if feat.size and feat.shape[0] == len(self.meta["feature_names"]):
                            prob = float(self.model.predict_proba(feat.reshape(1, -1))[0, 1])
                        else:
                            prob = 0.0
                        state = self._update_state(prob)
                        self._last_score = prob
                        row = {
                            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                            "state": "motion" if state else "idle",
                            "score": round(prob, 4),
                            "pps": round(self.client.observed_pps, 1),
                            "stream_gaps": self.client.stats["stream_gaps"],
                            "rssi_dbm": pkt.rssi_dbm,
                        }
                        self._log(row)
                        self.last_prediction = row
                        if self.on_prediction:
                            try:
                                self.on_prediction(row)
                            except Exception:
                                pass
                        print(f"\r[{row['timestamp'][-12:]}] "
                              f"{'● 有人移动' if state else '○ 无移动  '} "
                              f"score={prob:.2f} pps={row['pps']:.0f} "
                              f"gap={row['stream_gaps']}", end="")
                if self._stop_flag or (duration_s > 0 and time.time() - t0 >= duration_s):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.traffic.stop()
            try:
                self.control.set_sensing(traffic_generator_mode=prev_mode)
            except Exception:
                pass
            if self._csv_file:
                self._csv_file.close()
            print(f"\n[detector] 预测日志: {self.csv_path}")
