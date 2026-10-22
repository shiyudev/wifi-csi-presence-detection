#!/usr/bin/env python3
"""记录一段带标签的 CSI 数据。

用法:
    python scripts/record.py --host 192.168.1.50 --label walk --duration 30
    python scripts/record.py --host 192.168.1.50 --label empty --duration 60 --raw
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espectre_csi.recorder import RecordConfig, SessionRecorder  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="记录带标签的 CSI 会话")
    ap.add_argument("--host", required=True, help="ESPectre 设备 IP")
    ap.add_argument("--port", type=int, default=62587)
    ap.add_argument("--label", required=True,
                    help="动作标签: empty/static/walk/typing/page_turning/fan/...")
    ap.add_argument("--duration", type=float, default=30.0, help="时长(秒)")
    ap.add_argument("--pps", type=float, default=100.0, help="探测包速率")
    ap.add_argument("--description", default="", help="实验描述")
    ap.add_argument("--raw", action="store_true", help="同时保存原始 IQ 字节")
    ap.add_argument("--out", default="data", help="数据目录")
    args = ap.parse_args()

    rec = SessionRecorder(args.host, args.port, args.out)
    cfg = RecordConfig(label=args.label, description=args.description,
                       duration_s=args.duration, traffic_pps=args.pps,
                       save_raw=args.raw)

    def progress(elapsed, packets, pps):
        bar = "#" * int(elapsed / args.duration * 30)
        print(f"\r[{elapsed:6.1f}s] {packets:6d} 包 pps={pps:6.1f} |{bar:<30}|",
              end="")

    session = rec.record(cfg, on_progress=progress)
    print(f"\n会话目录: {session}")


if __name__ == "__main__":
    main()
