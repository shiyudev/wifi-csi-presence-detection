"""本地 Web 控制台：浏览器里完成 连接 / 实时曲线 / 采集 / 实时检测。

用法:
    python scripts/webui.py --port 8000
然后浏览器打开 http://127.0.0.1:8000

架构：
- StreamHub      一条 CSI 流 + 探测包，供所有浏览器订阅者共享 (SSE 推送)
- 采集/检测与实时曲线互斥（CSI 流同时只允许一个会话，官方固件限制）
- RealtimeDetector.stop() / on_prediction 已支持远程启停与状态读取
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from flask import Flask, Response, request

from .detector import RealtimeDetector
from .protocol import (
    DIRECT_HTTP_PORT, DeviceControl, CSIStreamClient, TrafficGenerator)

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = Path(__file__).parent / "dashboard.html"


class StreamHub:
    """共享 CSI 流：一个后台线程拉包，多个 SSE 订阅者排队收增量。"""

    def __init__(self):
        self.host = None
        self.client = None
        self.traffic = None
        self.control = None
        self.lock = threading.Lock()
        self.subs: set = set()
        self.stats = {"packets": 0, "gaps": 0, "pps": 0.0}
        self.note = "未连接"
        self._thread = None
        self._stop = False

    def connect(self, host: str) -> dict:
        info = DeviceControl(host, DIRECT_HTTP_PORT).device()
        with self.lock:
            self.host = host
        return info

    def ensure_started(self):
        """有订阅者且没有独占任务时启动流线程；独占任务结束后自动恢复。"""
        with self.lock:
            if self._thread and self._thread.is_alive():
                return
            if not self.host or app_state.recording_active or app_state.detector_active:
                return
            self.client = CSIStreamClient(self.host, DIRECT_HTTP_PORT, timeout=5)
            self.traffic = TrafficGenerator(self.host, pps=100.0)
            self.control = DeviceControl(self.host, DIRECT_HTTP_PORT)
            self._stop = False
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop = True
        for q in list(self.subs):
            q.put(("note", {"msg": "CSI 流被采集/检测任务占用，实时曲线暂停"}))
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self):
        try:
            self.control.wait_ready(timeout=5.0)
            prev = self.control.sensing().get("traffic_generator_mode", "ping")
            self.control.set_sensing(traffic_generator_mode="external")
            self.traffic.start()
            self._prev_mode = prev
            self.note = "实时曲线运行中"
            for pkt in self.client.packets():
                if self._stop:
                    break
                self.stats["packets"] += 1
                self.stats["gaps"] = self.client.stats["stream_gaps"]
                self.stats["pps"] = round(self.client.observed_pps, 1)
                payload = (pkt.timestamp,
                           [round(float(v), 1) for v in pkt.amplitudes])
                for q in list(self.subs):
                    q.put(("pkt", payload))
        except Exception as error:
            self.note = f"流错误: {error}"
        finally:
            try:
                self.traffic.stop()
                self.control.set_sensing(
                    traffic_generator_mode=getattr(self, "_prev_mode", "ping"))
            except Exception:
                pass
            self.note = "已断开（点连接设备重试）"

    def sse(self):
        q: queue.Queue = queue.Queue(maxsize=4000)
        self.subs.add(q)
        self.ensure_started()

        def gen():
            batch: list = []
            last_send = time.time()
            try:
                yield f"event: batch\ndata: []\n\n"
                while True:
                    try:
                        kind, item = q.get(timeout=10)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        continue
                    if kind == "note":
                        yield f"event: note\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                        continue
                    batch.append(item)
                    now = time.time()
                    if len(batch) >= 12 or now - last_send >= 0.1:
                        rows = [{"t": t, "a": a} for t, a in batch]
                        batch.clear()
                        last_send = now
                        yield f"event: batch\ndata: {json.dumps(rows)}\n\n"
            finally:
                self.subs.discard(q)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})


class AppState:
    def __init__(self):
        self.hub = StreamHub()
        self.rec_thread = None
        self.recorder = None
        self.rec_info = {}
        self.det_thread = None
        self.detector: RealtimeDetector | None = None
        self.det_threads: list = []   # 所有启动过的检测线程，防幽灵占流
        self.detectors: list = []     # 对应的检测器实例（stop 需要逐个停）

    @property
    def recording_active(self):
        return bool(self.rec_thread and self.rec_thread.is_alive())

    @property
    def detector_active(self):
        self.det_threads = [t for t in self.det_threads if t.is_alive()]
        return bool(self.det_threads)


app_state = AppState()
EVENTS: deque = deque(maxlen=100)
_event_id = [0]


def _log_event(msg):
    _event_id[0] += 1
    EVENTS.append({"id": _event_id[0],
                   "time": time.strftime("%H:%M:%S"), "msg": msg})
    print(f"[webui] {msg}", flush=True)


app = Flask(__name__)


@app.get("/")
def index():
    return DASHBOARD.read_text(encoding="utf-8")


@app.get("/api/stream")
def stream():
    return app_state.hub.sse()


@app.post("/api/connect")
def connect():
    host = (request.get_json(silent=True) or {}).get("host", "").strip()
    if not host:
        return {"ok": False, "error": "缺少设备 IP"}
    try:
        info = app_state.hub.connect(host)
        app_state.hub.note = "已连接，等待曲线订阅"
        app_state.hub.stop()          # 让 ensure_started 用新 host 重启
        _log_event(f"已连接设备 {host}（{info.get('chip', '?')} / {info.get('model', '?')}）")
        return {"ok": True, "chip": info.get("chip"), "model": info.get("model")}
    except Exception as error:
        return {"ok": False, "error": f"连接失败: {error}"}


@app.get("/api/status")
def status():
    rec = app_state.rec_info
    det = app_state.detector
    sessions_sig = _sessions_sig()
    return {
        "ok": True,
        "connected": bool(app_state.hub.host),
        "stream": app_state.hub.stats if app_state.hub.stats["packets"] else
                  {"packets": 0, "gaps": 0, "pps": 0.0},
        "note": app_state.hub.note,
        "recording": {
            "active": app_state.recording_active, **rec,
        },
        "detector": {
            "active": app_state.detector_active,
            "last": det.last_prediction if det else None,
        },
        "sessions": _list_sessions(),
        "sessions_sig": sessions_sig,
        "models": _list_models(),
        "events": list(EVENTS)[-15:],
    }


@app.post("/api/record/start")
def record_start():
    if app_state.recording_active:
        return {"ok": False, "error": "已有采集任务在运行"}
    if app_state.detector_active:
        return {"ok": False, "error": "检测运行中，请先停止"}
    body = request.get_json(silent=True) or {}
    host = app_state.hub.host
    if not host:
        return {"ok": False, "error": "请先连接设备"}
    from .recorder import RecordConfig, SessionRecorder
    app_state.hub.stop()
    cfg = RecordConfig(
        label=str(body.get("label", "unlabeled"))[:32],
        description=str(body.get("description", ""))[:200],
        duration_s=float(body.get("duration", 30)),
        traffic_pps=100.0,
    )
    recorder = SessionRecorder(host, DIRECT_HTTP_PORT, str(ROOT / "data"))
    app_state.recorder = recorder
    app_state.rec_info = {"label": cfg.label, "duration": cfg.duration_s,
                          "elapsed": 0.0, "packets": 0}

    def progress(elapsed, packets, pps):
        app_state.rec_info.update(elapsed=elapsed, packets=packets)

    def run():
        try:
            session = recorder.record(cfg, on_progress=progress)
            _log_event(f"采集完成: {Path(session).name}")
        except Exception as error:
            _log_event(f"采集失败: {error}")
        finally:
            app_state.rec_info = {}

    app_state.rec_thread = threading.Thread(target=run, daemon=True)
    app_state.rec_thread.start()
    _log_event(f"开始采集 [{cfg.label}] {cfg.duration_s}s")
    return {"ok": True}


@app.post("/api/record/stop")
def record_stop():
    was_active = bool(app_state.rec_info)
    if app_state.recorder:
        app_state.recorder.request_stop()
    if app_state.rec_thread:
        app_state.rec_thread.join(timeout=10)   # 等待写盘完成
        if was_active:
            _log_event("采集已停止（已采集部分数据已保存）")
    return {"ok": True}


@app.post("/api/detect/start")
def detect_start():
    if app_state.detector_active:
        return {"ok": False, "error": "检测已在运行"}
    if app_state.recording_active:
        return {"ok": False, "error": "采集运行中，请先停止"}
    body = request.get_json(silent=True) or {}
    model_name = body.get("model", "")
    model_path = ROOT / "models" / model_name
    if not model_path.exists():
        return {"ok": False, "error": f"模型不存在: {model_name}"}
    host = app_state.hub.host
    if not host:
        return {"ok": False, "error": "请先连接设备"}
    app_state.hub.stop()
    det = RealtimeDetector(host, model_path, out_dir=str(ROOT / "outputs"),
                           score_threshold=float(body.get("threshold", 0.5)))
    app_state.detector = det
    det.on_prediction = lambda row: None

    def run():
        try:
            det.run(duration_s=0)
            _log_event(f"检测结束, 日志: {det.csv_path.name}")
        except Exception as error:
            _log_event(f"检测失败: {error}")

    th = threading.Thread(target=run, daemon=True)
    app_state.det_threads.append(th)
    app_state.detectors.append(det)
    app_state.det_thread = th
    th.start()
    _log_event(f"实时检测已启动（模型 {model_name}, 阈值 {det.score_threshold}）")
    return {"ok": True}


@app.post("/api/detect/stop")
def detect_stop():
    # 停掉所有检测实例（含历史遗留线程）并等待其退出、释放 CSI 流
    for det in app_state.detectors:
        det.stop()
    for t in app_state.det_threads:
        t.join(timeout=20)
    app_state.det_threads = [t for t in app_state.det_threads if t.is_alive()]
    app_state.detectors = []
    # 给设备一点时间释放上一个 CSI 会话，避免后续 PATCH 409
    time.sleep(2)
    return {"ok": True}


def _list_sessions():
    data = ROOT / "data"
    out = []
    if data.exists():
        for p in sorted(data.iterdir(), reverse=True):
            meta = p / "meta.json"
            if p.is_dir() and meta.exists():
                try:
                    m = json.loads(meta.read_text(encoding="utf-8"))
                    out.append({"name": p.name, "label": m.get("label", "?"),
                                "packets": m.get("packet_count", 0)})
                except Exception:
                    pass
    return out[:30]


def _sessions_sig():
    return hash(tuple((s["name"], s["packets"]) for s in _list_sessions()))


def _list_models():
    models = ROOT / "models"
    return sorted(p.name for p in models.glob("*.joblib")) if models.exists() else []


def main():
    from argparse import ArgumentParser
    ap = ArgumentParser(description="CSI Web 控制台")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"控制台地址: http://127.0.0.1:{args.port}")
    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
