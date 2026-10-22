#!/usr/bin/env python3
"""实时运行检测器：接收 CSI 流 → 滑动窗口推理 → 打印并保存判断。

用法:
    python scripts/run_detector.py --host 192.168.1.50 --model models/detector.joblib

输出:
    终端实时状态行
    outputs/predictions_<时间戳>.csv / .jsonl  预测日志
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espectre_csi.detector import RealtimeDetector  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="实时有人移动检测")
    ap.add_argument("--host", required=True)
    ap.add_argument("--model", default="models/detector.joblib")
    ap.add_argument("--duration", type=float, default=0.0,
                    help="运行秒数, 0=直到 Ctrl+C")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--hysteresis", type=int, default=2,
                    help="连续 N 次判断一致才切换状态")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()

    det = RealtimeDetector(args.host, args.model, out_dir=args.out,
                           score_threshold=args.threshold,
                           hysteresis=args.hysteresis)
    det.run(duration_s=args.duration)


if __name__ == "__main__":
    main()
