#!/usr/bin/env python3
"""实时观察 CSI 子载波曲线（与 espectre.dev/tools/csi-visualizer 等效，
但数据同时可被本地保存与训练流水线直接消费）。

用法:
    python scripts/live_view.py --host 192.168.1.50
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espectre_csi.viz import LiveViewer  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="实时 CSI 曲线")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=62587)
    ap.add_argument("--window", type=float, default=10.0, help="显示窗口时长(秒)")
    ap.add_argument("--pps", type=float, default=100.0)
    ap.add_argument("--sc", default=None,
                    help="指定子载波, 如 3,11,27,43；默认自动挑变化最大的 8 个")
    ap.add_argument("--no-smooth", action="store_true", help="关闭滑动平均")
    ap.add_argument("--snapshot-dir", default=None,
                    help="定期把当前图保存为 PNG（保留最近 10 张）")
    args = ap.parse_args()

    subcarriers = ([int(x) for x in args.sc.split(",")]
                   if args.sc else None)
    LiveViewer(args.host, args.port, duration_s=args.window,
               traffic_pps=args.pps, subcarriers=subcarriers,
               smooth_s=0.0 if args.no_smooth else 0.2,
               snapshot_dir=args.snapshot_dir).run()


if __name__ == "__main__":
    main()
