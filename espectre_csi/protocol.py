"""ESPectre Direct HTTP 协议实现。

协议来源（已核对固件源码与官方 Python 工具）：
- src/cpp/runtime/csi_raw_record.h   —— V8 记录头 (64 字节)
- tools/lib/csi_io.py               —— HTTP 帧前缀 (60 字节) 与解析逻辑
- docs/API.md, docs/CSI.md          —— 端点、外部流量、质量规则

流格式：GET http://<ip>:62587/espectre/v1/csi
  每帧 = 60B 帧前缀 + 64B V8 记录头 + csi_len 字节 IQ 载荷
  IQ 顺序 [Q0, I0, Q1, I1, ...]，int8，64 子载波 = 128 字节
外部流量：UDP 5555 端口，载荷必须是 4 字节 0xF0 9F 91 BB
"""

from __future__ import annotations

import http.client
import json
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import numpy as np

# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------

DIRECT_HTTP_PORT = 62587          # Direct HTTP 服务端口 (0xF47B)
RAW_CSI_PATH = "/espectre/v1/csi"
EVENTS_PATH = "/espectre/v1/events"

RAW_CSI_PROTOCOL_VERSION = 1
RAW_CSI_RECORD_VERSION_V8 = 8
RAW_CSI_RESPONSE_MAGIC = 0x52505345          # "EPSR" (little-endian)
RAW_CSI_RECORD_MAGIC = 0x4353                # "SC"
RAW_CSI_MAX_PAYLOAD_BYTES = 512

# HTTP 帧前缀: <IBBH16sQHHQQQ = 60 字节
RAW_CSI_HTTP_FRAME_STRUCT = struct.Struct("<IBBH16sQHHQQQ")
# V8 记录头: <HBBBBIHHQQIQBbbQIIBBB = 64 字节
CSI_HEADER_STRUCT = struct.Struct("<HBBBBIHHQQIQBbbQIIBBB")

# 外部探测流量
TRAFFIC_UDP_PORT = 5555
TRAFFIC_MARKER = b"\xf0\x9f\x91\xbb"         # "👻".encode("utf-8")

RAW_CSI_FLAG_FIRST_WORD_INVALID = 1 << 0
RAW_CSI_FLAG_WIFI_RX_TS_VALID = 1 << 1
RAW_CSI_FLAG_WIFI_RX_START_TS_NS_VALID = 1 << 2
RAW_CSI_FLAG_FRESH = 1 << 3

NOISE_FLOOR_INVALID_DBM = -128

CHIP_CODES = {0: "unknown", 1: "ESP32", 2: "S2", 3: "S3", 4: "C3", 5: "C5", 6: "C6"}
PHY_MODE_CODES = {0: "unknown", 1: "legacy", 2: "ht", 3: "vht", 4: "he-su",
                  5: "he-mu", 6: "he-ersu", 7: "he-tb"}
LTF_TYPE_CODES = {0: "unknown", 1: "lltf", 2: "ht-ltf", 3: "vht-ltf", 4: "he-ltf"}
CHANNEL_WIDTH_CODES = {0: "unknown", 1: "20", 2: "40", 3: "80", 4: "160", 5: "80+80"}

DETECTOR_READY_STATES = ("ready",)


# ---------------------------------------------------------------------------
# 数据包
# ---------------------------------------------------------------------------


@dataclass
class CSIPacket:
    """一条解析后的原始 CSI 记录。"""

    timestamp: float                 # 电脑接收时刻 (Unix 秒)
    seq_num: int
    num_subcarriers: int
    iq_raw: np.ndarray               # int8 [num_subcarriers * 2]
    record_version: int
    chip: str
    device_id: Optional[int]
    device_ticks_us: Optional[int]
    channel: int
    rssi_dbm: int
    noise_floor_dbm: Optional[int]
    phy_mode: str
    ltf_type: str
    channel_width: str
    csi_fresh: bool
    amplitudes: Optional[np.ndarray] = None   # float32 [num_subcarriers]
    phases: Optional[np.ndarray] = None       # float32 [num_subcarriers]
    # 会话计数器（用于丢包诊断）
    stream_sequence: int = 0
    fresh_record_total: int = 0
    raw_drop_total: int = 0
    send_backpressure_total: int = 0


def parse_csi_record(data: bytes, offset: int = 0, *, timestamp: Optional[float] = None) -> tuple:
    """解析一条 V8 CSI 记录，返回 (CSIPacket|None, 下一个偏移)。"""
    if len(data) - offset < CSI_HEADER_STRUCT.size:
        return None, offset
    (magic, version, header_len, chip_code, flags, seq_num, num_sc, csi_len,
     device_id, device_ticks_us, wifi_rx_ts_us, wifi_rx_start_ts_ns,
     channel, rssi_dbm, noise_floor_dbm, transport_counter, fresh_counter,
     request_counter, phy_mode_code, ltf_type_code, channel_width_code) = \
        CSI_HEADER_STRUCT.unpack_from(data, offset)

    if magic != RAW_CSI_RECORD_MAGIC or version != RAW_CSI_RECORD_VERSION_V8:
        return None, offset
    if csi_len == 0 or csi_len != num_sc * 2:
        return None, offset
    record_len = header_len + csi_len
    if len(data) - offset < record_len:
        return None, offset

    iq_raw = np.frombuffer(data, dtype=np.int8, count=csi_len,
                           offset=offset + header_len).copy()
    q = iq_raw[0::2].astype(np.float32)
    i = iq_raw[1::2].astype(np.float32)
    complex_iq = (i + 1j * q).astype(np.complex64)
    amplitudes = np.abs(complex_iq)
    phases = np.angle(complex_iq)

    packet = CSIPacket(
        timestamp=time.time() if timestamp is None else float(timestamp),
        seq_num=int(seq_num),
        num_subcarriers=int(num_sc),
        iq_raw=iq_raw,
        record_version=int(version),
        chip=CHIP_CODES.get(chip_code, "unknown"),
        device_id=int(device_id) or None,
        device_ticks_us=int(device_ticks_us) or None,
        channel=int(channel),
        rssi_dbm=int(rssi_dbm),
        noise_floor_dbm=None if int(noise_floor_dbm) == NOISE_FLOOR_INVALID_DBM else int(noise_floor_dbm),
        phy_mode=PHY_MODE_CODES.get(phy_mode_code, "unknown"),
        ltf_type=LTF_TYPE_CODES.get(ltf_type_code, "unknown"),
        channel_width=CHANNEL_WIDTH_CODES.get(channel_width_code, "unknown"),
        csi_fresh=bool(flags & RAW_CSI_FLAG_FRESH),
        amplitudes=amplitudes,
        phases=phases,
        fresh_record_total=min(int(fresh_counter), 0xFFFFFFFF),
        send_backpressure_total=int(transport_counter),
    )
    return packet, offset + record_len


# ---------------------------------------------------------------------------
# REST 辅助（/health /device /sensing /diagnostics）
# ---------------------------------------------------------------------------


class DeviceControl:
    """ESPectre Direct HTTP 控制接口（JSON 资源与命令）。"""

    def __init__(self, host: str, port: int = DIRECT_HTTP_PORT, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            payload = json.dumps(body) if body is not None else None
            # 固件 3.0.0 起所有端点都要求 Origin 头，否则返回 403
            headers = {"Origin": "https://espectre.dev"}
            if payload:
                headers["Content-Type"] = "application/json"
            conn.request(method, f"/espectre/v1{path}", body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status not in (200, 202):
                raise RuntimeError(f"{method} {path} -> HTTP {resp.status}: {raw[:200]!r}")
            return json.loads(raw) if raw else {}
        finally:
            conn.close()

    # --- 常用封装 -------------------------------------------------------

    def health(self) -> dict:
        return self.request("GET", "/health")

    def device(self) -> dict:
        return self.request("GET", "/device")

    def sensing(self) -> dict:
        return self.request("GET", "/sensing")

    def diagnostics(self, fields: Optional[list] = None) -> dict:
        if fields:
            return self.request("GET", f"/diagnostics?fields={','.join(fields)}")
        return self.request("GET", "/diagnostics")

    def set_sensing(self, **fields) -> dict:
        """PATCH /sensing，例如 set_sensing(traffic_generator_mode='external')。"""
        return self.request("PATCH", "/sensing", fields)

    def wait_ready(self, timeout: float = 30.0, poll: float = 0.5) -> dict:
        """等待检测器就绪（校准完成）。

        兼容两种固件响应：旧版有 state 字段；3.0.0 返回
        mode="sensing" + ready=true（无 state 字段）。
        """
        deadline = time.time() + timeout
        last = {}
        while time.time() < deadline:
            last = self.sensing()
            state = str(last.get("state", "")).lower()
            mode = str(last.get("mode", "")).lower()
            if (state in DETECTOR_READY_STATES and last.get("ready", True)) \
                    or (mode in ("sensing", "ready") and last.get("ready")):
                return last
            time.sleep(poll)
        return last


# ---------------------------------------------------------------------------
# 外部探测流量生成器
# ---------------------------------------------------------------------------


class TrafficGenerator:
    """以固定速率向设备发送 UDP 探测标记（external 模式必需）。

    载荷必须是 4 字节 F0 9F 91 BB，端口 5555。
    """

    def __init__(self, host: str, pps: float = 100.0, port: int = TRAFFIC_UDP_PORT):
        self.host = host
        self.pps = float(pps)
        self.port = port
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.sent = 0

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        interval = 1.0 / self.pps

        def run():
            next_t = time.perf_counter()
            while not self._stop.is_set():
                now = time.perf_counter()
                next_t += interval
                wait = next_t - now
                if wait > 0:
                    time.sleep(wait)
                else:
                    # 落后了就重新对齐，避免突发补偿
                    next_t = now + interval
                try:
                    sock.sendto(TRAFFIC_MARKER, (self.host, self.port))
                    self.sent += 1
                except OSError:
                    break
            sock.close()

        self._thread = threading.Thread(target=run, daemon=True, name="traffic-gen")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None


# ---------------------------------------------------------------------------
# CSI 流接收器
# ---------------------------------------------------------------------------


class CSIStreamClient:
    """连接 GET /espectre/v1/csi，解析帧并逐包回调。

    用法：
        client = CSIStreamClient("192.168.1.50")
        for packet in client.packets():
            ...
    """

    def __init__(self, host: str, port: int = DIRECT_HTTP_PORT, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.session_id = b""
        self.stats = {
            "frames": 0, "packets": 0, "parse_errors": 0,
            "stream_gaps": 0, "bytes": 0, "start_time": None,
        }

    def packets(self, retry: bool = False) -> Iterator[CSIPacket]:
        """阻塞迭代 CSI 包；网络断开或协议错误时抛异常。

        retry=True 时流中断自动重连（用于实时可视化等长驻场景）。
        """
        while True:
            try:
                yield from self._packets_once()
            except (http.client.IncompleteRead, ConnectionError, socket.timeout,
                    OSError) as e:
                if not retry:
                    raise
                print(f"[protocol] CSI 流中断 ({type(e).__name__})，1 秒后重连...",
                      flush=True)
                time.sleep(1.0)

    def _packets_once(self) -> Iterator[CSIPacket]:
        """单次连接迭代 CSI 包；断流或协议错误时抛异常。"""
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        buffer = bytearray()
        stream_sequence = -1
        fresh_total = -1
        self.session_id = b""   # 每次连接会话 ID 会变化，需重置
        self.stats["start_time"] = time.time()
        try:
            conn.request("GET", RAW_CSI_PATH,
                         headers={"Origin": "https://espectre.dev"})
            resp = conn.getresponse()
            if resp.status != 200:
                body = resp.read(200)
                raise RuntimeError(f"CSI 流打开失败: HTTP {resp.status} {body!r}")
            while True:
                try:
                    chunk = resp.read(4096)
                except (TimeoutError, socket.timeout):
                    # 空闲超时：视为流结束（外部流量中断时会触发）
                    break
                if not chunk:
                    break
                self.stats["bytes"] += len(chunk)
                buffer.extend(chunk)
                # 逐帧消费
                while len(buffer) >= RAW_CSI_HTTP_FRAME_STRUCT.size:
                    (magic, version, record_version, header_len, session_id,
                     seq64, record_len, flags, ft, rdt, bpt) = \
                        RAW_CSI_HTTP_FRAME_STRUCT.unpack_from(buffer, 0)
                    frame_length = header_len + record_len
                    if len(buffer) < frame_length:
                        break
                    if not self.session_id and len(session_id) == 16:
                        self.session_id = bytes(session_id)
                    if (magic != RAW_CSI_RESPONSE_MAGIC
                            or version != RAW_CSI_PROTOCOL_VERSION
                            or record_version != RAW_CSI_RECORD_VERSION_V8
                            or header_len != RAW_CSI_HTTP_FRAME_STRUCT.size
                            or session_id != self.session_id
                            or flags != 0):
                        raise RuntimeError("收到不兼容的 HTTP 帧（固件版本不匹配？）")
                    if stream_sequence >= 0 and seq64 > stream_sequence + 1:
                        self.stats["stream_gaps"] += seq64 - stream_sequence - 1
                    stream_sequence = seq64
                    fresh_total = ft
                    self.stats["frames"] += 1
                    frame = bytes(buffer[:frame_length])
                    del buffer[:frame_length]

                    packet, next_off = parse_csi_record(frame, header_len)
                    if packet is None or next_off != len(frame):
                        self.stats["parse_errors"] += 1
                        continue
                    packet.stream_sequence = int(seq64)
                    packet.raw_drop_total = int(rdt)
                    self.stats["packets"] += 1
                    yield packet
        finally:
            conn.close()

    @property
    def observed_pps(self) -> float:
        if not self.stats["start_time"] or not self.stats["packets"]:
            return 0.0
        return self.stats["packets"] / max(1e-9, time.time() - self.stats["start_time"])


def iq_to_amplitude_matrix(iq_rows: np.ndarray) -> np.ndarray:
    """把 int8 [N, SC*2] 的 IQ 块转为 float32 幅度矩阵 [N, SC]。

    IQ 顺序为 [Q0, I0, Q1, I1, ...]。
    """
    q = iq_rows[:, 0::2].astype(np.float32)
    i = iq_rows[:, 1::2].astype(np.float32)
    return np.sqrt(i * i + q * q)
