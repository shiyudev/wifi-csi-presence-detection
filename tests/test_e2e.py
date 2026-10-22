#!/usr/bin/env python3
"""端到端测试：模拟器 → 采集 → 训练 → 实时检测 → 结果文件检查。

运行: python tests/test_e2e.py
"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sim_device import start_simulator, sim_state  # noqa: E402

from espectre_csi.features import WindowConfig, cut_windows  # noqa: E402
from espectre_csi.features import features_for_window, feature_names  # noqa: E402
from espectre_csi.model import (build_dataset, evaluate, session_split,  # noqa: E402
                                save_model, train_models)
from espectre_csi.recorder import RecordConfig, SessionRecorder, load_session  # noqa: E402
from espectre_csi.detector import RealtimeDetector  # noqa: E402


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        raise AssertionError(name)


def main():
    print("== 1. 启动设备模拟器 ==")
    start_simulator()
    time.sleep(0.5)

    print("== 2. 协议往返测试 ==")
    rec = SessionRecorder("127.0.0.1", 62587, str(ROOT / "data"))
    cfg = RecordConfig(label="empty", description="e2e idle", duration_s=6.0)
    s1 = rec.record(cfg)
    sim_state["motion"] = True
    cfg2 = RecordConfig(label="walk", description="e2e motion", duration_s=6.0)
    s2 = rec.record(cfg2)
    sim_state["motion"] = False

    sess = load_session(s1)
    check("会话可读取且标签正确", sess["label"] == "empty")
    check("幅度矩阵形状正确", sess["amplitudes"].ndim == 2)
    n_sc = sess["amplitudes"].shape[1]
    check("子载波数 = 64", n_sc == 64)
    pps = len(sess["times"]) / (sess["times"][-1] - sess["times"][0])
    check(f"采集速率合理 (pps={pps:.0f})", 40 <= pps <= 200)
    # motion 会话方差应显著高于 idle
    m = load_session(s2)
    check("motion 会话方差 > idle 会话方差",
          m["amplitudes"].var() > sess["amplitudes"].var())

    print("== 3. 特征提取测试 ==")
    wcfg = WindowConfig(window_s=2.0, step_s=0.5)
    wins = cut_windows(sess["times"], sess["amplitudes"], wcfg)
    check("窗口数量 > 5", len(wins) > 5)
    f = features_for_window(wins[0][1])
    check(f"特征维度 = {len(feature_names(n_sc))}", len(f) == len(feature_names(n_sc)))
    check("特征无 NaN", np.isfinite(f).all())

    print("== 4. 训练测试 ==")
    # 4 个会话：2 空 + 2 走动，保证会话级划分后训练集两类都有
    sessions = [s1, s2]
    for label in ("empty", "walk"):
        sim_state["motion"] = (label == "walk")
        sessions.append(rec.record(
            RecordConfig(label=label, description="e2e", duration_s=4.0)))
    sim_state["motion"] = False
    sess_paths = [Path(p) for p in sessions]
    X, y, sids, n_sc2 = build_dataset(sess_paths, wcfg)
    check("数据集构建成功", len(X) == len(y) == len(sids))
    train_mask, test_mask = session_split(len(sess_paths), sids, 0.5, 42)
    results = train_models(X, y, train_mask, train_mask)
    best_name = max(results, key=lambda k: results[k]["val_accuracy"])
    print(f"  候选模型验证准确率: "
          f"{ {k: round(v['val_accuracy'], 3) for k, v in results.items()} }")
    best = results[best_name]["model"]
    ev = evaluate(best, X[test_mask], y[test_mask])
    print(f"  测试集评估: acc={ev['accuracy']:.2f}")
    model_path = ROOT / "models" / "e2e_model.joblib"
    save_model(model_path, best, n_sc2, wcfg, results[best_name]["val_accuracy"],
               sess_paths, extra={"best": best_name})
    check("模型文件已保存", model_path.exists())

    print("== 5. 实时检测测试 ==")
    out_dir = ROOT / "outputs"
    det = RealtimeDetector("127.0.0.1", model_path, out_dir=out_dir,
                           window_cfg=wcfg)
    # 前 4 秒无移动，后 4 秒模拟移动
    import threading
    timer = threading.Timer(4.0, lambda: sim_state.update(motion=True))
    timer.start()
    det.run(duration_s=8.0)
    csv_path = det.csv_path
    rows = list(csv.DictReader(open(csv_path)))
    check("预测日志非空", len(rows) > 5)
    preds = {r["state"] for r in rows}
    check(f"预测含两种状态 {preds}", preds == {"idle", "motion"})
    jrow = json.loads(open(csv_path.with_suffix(".jsonl")).readline())
    check("JSONL 日志含 score 字段", "score" in jrow)

    print("\n全部端到端测试通过 ✔")


if __name__ == "__main__":
    main()
