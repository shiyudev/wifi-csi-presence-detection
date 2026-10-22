#!/usr/bin/env python3
"""训练"有移动/无移动"检测模型。

用法:
    python scripts/train.py --data data --out models/detector.joblib

流程: 读会话 -> 切窗口提特征 -> 按会话划分训练/测试(FR-12) ->
      训练多个候选模型 -> 测试集评估 -> 保存模型 + 评测报告
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espectre_csi.features import WindowConfig  # noqa: E402
from espectre_csi.model import (build_dataset, evaluate, load_session,  # noqa: E402
                                save_model, session_split, train_models)


def main():
    ap = argparse.ArgumentParser(description="训练存在/移动检测模型")
    ap.add_argument("--data", default="data", help="会话数据目录")
    ap.add_argument("--out", default="models/detector.joblib", help="模型输出路径")
    ap.add_argument("--window", type=float, default=2.0, help="窗口时长(秒)")
    ap.add_argument("--step", type=float, default=0.5, help="滑动步长(秒)")
    ap.add_argument("--test-ratio", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data)
    sessions = sorted(p for p in data_dir.iterdir()
                      if p.is_dir() and (p / "csi.npz").exists())
    if not sessions:
        sys.exit(f"错误: {data_dir} 下没有会话数据，先用 scripts/record.py 采集")

    cfg = WindowConfig(window_s=args.window, step_s=args.step)
    X, y, sids, n_sc = build_dataset(sessions, cfg)
    print(f"[train] 总计 {len(X)} 个窗口, 特征维度 {X.shape[1]}, "
          f"motion={int((y==1).sum())} idle={int((y==0).sum())}")

    train_mask, test_mask = session_split(len(sessions), sids,
                                          args.test_ratio, args.seed)
    # 从训练集中再切 20% 做验证（用于模型选择）
    tr_ids = sids[train_mask]
    uniq = np_unique = sorted(set(tr_ids.tolist()))
    import numpy as np
    rng = np.random.default_rng(args.seed)
    rng.shuffle(np_unique)
    n_val = max(1, int(len(np_unique) * 0.25)) if len(np_unique) > 1 else 0
    val_ids = set(np_unique[:n_val])
    val_mask = train_mask & np.isin(sids, list(val_ids))
    train_only_mask = train_mask & ~np.isin(sids, list(val_ids))
    if not train_only_mask.any() or not val_mask.any():
        train_only_mask, val_mask = train_mask, train_mask

    results = train_models(X, y, train_only_mask, val_mask)
    best_name = max(results, key=lambda k: results[k]["val_accuracy"])
    best = results[best_name]["model"]
    print(f"[train] 选择模型: {best_name}")

    test_eval = evaluate(best, X[test_mask], y[test_mask])
    print(f"[train] 测试集: {json.dumps(test_eval, ensure_ascii=False)}")

    save_model(args.out, best, n_sc, cfg, results[best_name]["val_accuracy"],
               [s.name for s in sessions],
               extra={"best_model": best_name, "test_eval": test_eval,
                      "window": args.window, "step": args.step})

    report = {
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sessions": [s.name for s in sessions],
        "windows_total": int(len(X)),
        "best_model": best_name,
        "candidates": {k: {"val_accuracy": v["val_accuracy"]}
                       for k, v in results.items()},
        "test_eval": test_eval,
    }
    out = Path(args.out)
    report_path = out.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"[train] 模型: {out}\n[train] 评测报告: {report_path}")


if __name__ == "__main__":
    main()
