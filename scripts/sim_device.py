#!/usr/bin/env python3
"""ESPectre 设备模拟器 —— 无真机时验证整条工具链。

严格按官方协议实现（可被本工具链的解析器直接解析）：
- GET  /espectre/v1/health | /device | /sensing | /diagnostics
- PATCH /espectre/v1/sensing            切换 traffic_generator_mode
- GET  /espectre/v1/csi                 chunked 二进制 CSI 流 (V8)
- UDP 5555                              探测标记（收到 1 个标记生成 1 条记录）

CSI 生成模型：
- idle : 每子载波固定增益 + 微小噪声
- motion: 部分子载波叠加 0.8~3Hz 正弦调制 + 更大噪声
通过修改 sim_state["motion"] 切换两种状态。

用法: python scripts/sim_device.py [--port 62587]
"""
import argparse
import json
import socket
import struct
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

DIRECT_HTTP_PORT = 62587
TRAFFIC_UDP_PORT = 5555
RAW_CSI_RESPONSE_MAGIC = 0x52505345
FRAME_STRUCT = struct.Struct("<IBBH16sQHHQQQ")
HEADER_STRUCT = struct.Struct("<HBBBBIHHQQIQBbbQIIBBB")
SESSION_ID = bytes(range(16))
TRAFFIC_MARKER = b"\xf0\x9f\x91\xbb"

N_SC = 64
rng = np.random.default_rng(7)

# 全局模拟状态（测试代码可直接修改）
sim_state = {
    "motion": False,
    "traffic_generator_mode": "ping",
    "stream_sequence": 0,
    "fresh_total": 0,
}
_record_queue: deque = deque()
_queue_lock = threading.Lock()

# 每子载波静态增益与相位（模拟固定房间响应）
BASE_GAIN = rng.uniform(40, 90, N_SC).astype(np.float32)
BASE_PHASE = rng.uniform(-np.pi, np.pi, N_SC).astype(np.float32)
MOTION_SC = rng.choice(N_SC, size=20, replace=False)   # 运动敏感子载波
MOTION_FREQ = rng.uniform(0.8, 3.0, N_SC)


def make_record(ts_unix: float) -> bytes:
    """生成一条完整 HTTP 帧：60B 前缀 + 64B 记录头 + 128B IQ。"""
    t_rel = ts_unix % 1000
    gain = BASE_GAIN.copy()
    if sim_state["motion"]:
        mod = 1.0 + 0.18 * np.sin(2 * np.pi * MOTION_FREQ * t_rel)
        gain[MOTION_SC] *= mod[MOTION_SC]
    amp = gain + rng.normal(0, 1.0 if not sim_state["motion"] else 2.5, N_SC)
    phase = BASE_PHASE + rng.normal(0, 0.02, N_SC) + 0.01 * t_rel
    i = np.clip(amp * np.cos(phase), -127, 127).astype(np.int8)
    q = np.clip(amp * np.sin(phase), -127, 127).astype(np.int8)
    iq = np.empty(N_SC * 2, dtype=np.int8)
    iq[0::2], iq[1::2] = q, i                      # [Q0, I0, Q1, I1, ...]

    sim_state["stream_sequence"] += 1
    sim_state["fresh_total"] += 1
    seq = sim_state["stream_sequence"] & 0xFFFF
    device_ticks = int((ts_unix % 3600) * 1e6)

    header = HEADER_STRUCT.pack(
        0x4353, 8, 64, 1, 1 << 3,                     # magic, ver, hlen, chip, flags(u8)
        seq, N_SC, N_SC * 2,                          # seq(u32), num_sc, csi_len
        1, device_ticks,                              # device_id, device_ticks(u64)
        int(ts_unix * 1e6) & 0xFFFFFFFF, 0,           # wifi_rx_ts(u32), start_ts(u64)
        6, -52, -95,                                  # channel, rssi, noise(int8)
        0,                                            # backpressure(u64)
        sim_state["fresh_total"] & 0xFFFFFFFF,
        sim_state["fresh_total"] & 0xFFFFFFFF,
        2, 2, 1,                                      # phy, ltf, width
    )
    frame_prefix = FRAME_STRUCT.pack(
        RAW_CSI_RESPONSE_MAGIC, 1, 8, 60, SESSION_ID,
        sim_state["stream_sequence"] & 0xFFFFFFFFFFFFFFFF,
        64 + N_SC * 2, 0,
        sim_state["fresh_total"] & 0xFFFFFFFFFFFFFFFF, 0, 0,
    )
    return frame_prefix + header + iq.tobytes()


def udp_listener():
    """收到一个探测标记 → 生成一条 CSI 记录入队。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", TRAFFIC_UDP_PORT))
    while True:
        data, _ = sock.recvfrom(64)
        if data == TRAFFIC_MARKER:
            with _queue_lock:
                _record_queue.append(make_record(time.time()))


class SimHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/espectre/v1/health":
            self._json(200, {"state": "ready", "uptime_ms": 123456})
        elif self.path == "/espectre/v1/device":
            self._json(200, {"chip": "ESP32", "model": "sim", "label": "sim-device",
                             "version": "test"})
        elif self.path == "/espectre/v1/sensing":
            self._json(200, {"state": "ready", "ready": True,
                             "traffic_generator_mode": sim_state["traffic_generator_mode"],
                             "csi_target_pps": 100})
        elif self.path == "/espectre/v1/diagnostics":
            self._json(200, {"raw_drop_total": 0})
        elif self.path == "/espectre/v1/csi":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                while True:
                    frame = None
                    with _queue_lock:
                        if _record_queue:
                            frame = _record_queue.popleft()
                    if frame is not None:
                        self.wfile.write(f"{len(frame):x}\r\n".encode())
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    else:
                        time.sleep(0.005)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        else:
            self._json(404, {"error": "not found"})

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        if self.path == "/espectre/v1/sensing":
            if "traffic_generator_mode" in body:
                sim_state["traffic_generator_mode"] = body["traffic_generator_mode"]
            self._json(200, {"state": "ready", "ready": True,
                             "traffic_generator_mode": sim_state["traffic_generator_mode"]})
        else:
            self._json(404, {"error": "not found"})


def start_simulator(port: int = DIRECT_HTTP_PORT):
    threading.Thread(target=udp_listener, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), SimHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DIRECT_HTTP_PORT)
    ap.add_argument("--motion", action="store_true", help="启动即进入 motion 状态")
    args = ap.parse_args()
    sim_state["motion"] = args.motion
    start_simulator(args.port)
    print(f"模拟器运行中: http://127.0.0.1:{args.port}/espectre/v1/health "
          f"(motion={sim_state['motion']})")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
