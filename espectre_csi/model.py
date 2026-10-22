"""模型训练与保存。

策略（对应 PRD：模型在电脑上训练，本地可复现）：
- 主模型：标准化特征 + 随机森林（样本量小时稳健、可解释、训练快）
- 备选模型：RBF SVM 与 MLP，训练脚本会自动对比并选验证集最优
- 二分类目标：motion（有移动）vs idle（无移动）

标签归并（训练时可配置）：
    motion 类: walk, typing, page_turning, ...
    idle   类: empty, static, fan, robot_vacuum, ...
注意：empty（无人）与 static（有人静止）都归 idle——
第一版模型判断的是"有移动/无移动"，静止人员检测属于长期目标。

FR-12 防泄漏：按"会话"划分训练/测试集，同一会话的窗口不会同时
出现在两边。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .features import WindowConfig, cut_windows, feature_names, features_for_window
from .recorder import load_session

DEFAULT_MOTION_LABELS = {"walk", "typing", "page_turning", "motion", "exercise"}
DEFAULT_IDLE_LABELS = {"empty", "static", "fan", "robot_vacuum", "idle"}


def label_to_binary(label: str,
                    motion_labels: Optional[set] = None,
                    idle_labels: Optional[set] = None) -> Optional[int]:
    motion_labels = motion_labels or DEFAULT_MOTION_LABELS
    idle_labels = idle_labels or DEFAULT_IDLE_LABELS
    if label in motion_labels:
        return 1
    if label in idle_labels:
        return 0
    return None


def build_dataset(session_dirs: List[Path], cfg: WindowConfig) -> Tuple[np.ndarray, ...]:
    """从会话列表构建 (X, y, session_id, feature_dim)。

    X: [M, D] 特征, y: [M] 二分类标签, session_id: [M] 会话索引。
    """
    Xs, ys, sids = [], [], []
    n_sc = None
    for sid, d in enumerate(session_dirs):
        if not (Path(d) / "csi.npz").exists():
            print(f"[dataset] 跳过 {Path(d).name}: 没有 csi.npz（采集中或已损坏）")
            continue
        sess = load_session(d)
        y_bin = label_to_binary(sess["label"])
        if y_bin is None:
            print(f"[dataset] 跳过 {d.name}: 标签 '{sess['label']}' 无法归并到 motion/idle")
            continue
        windows = cut_windows(sess["times"], sess["amplitudes"], cfg)
        feats = [features_for_window(w) for _, w in windows]
        feats = [f for f in feats if f.size]
        if not feats:
            print(f"[dataset] 跳过 {d.name}: 窗口不足")
            continue
        if n_sc is None:
            n_sc = (len(feats[0]) - 6) // 2
        Xs.append(np.stack(feats))
        ys.append(np.full(len(feats), y_bin, dtype=np.int64))
        sids.append(np.full(len(feats), sid, dtype=np.int64))
        print(f"[dataset] {d.name}: label={sess['label']} -> {'motion' if y_bin else 'idle'}, "
              f"{len(feats)} 窗口")
    if not Xs:
        raise RuntimeError("没有可用数据：请先采集带标签的会话")
    return np.vstack(Xs), np.concatenate(ys), np.concatenate(sids), n_sc


def session_split(n_sessions: int, session_ids: np.ndarray,
                  test_ratio: float = 0.3, seed: int = 42):
    """按会话划分训练/测试索引（FR-12）。"""
    rng = np.random.default_rng(seed)
    ids = np.arange(n_sessions)
    rng.shuffle(ids)
    n_test = max(1, int(round(n_sessions * test_ratio)))
    test_ids = set(ids[:n_test].tolist())
    test_mask = np.isin(session_ids, list(test_ids))
    return ~test_mask, test_mask


def train_models(X: np.ndarray, y: np.ndarray, train_mask: np.ndarray,
                 val_mask: np.ndarray) -> dict:
    """在同一训练集上训练多个候选模型，按验证集准确率选择。"""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    Xtr, ytr = X[train_mask], y[train_mask]
    Xva, yva = X[val_mask], y[val_mask]
    candidates = {
        "random_forest": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=200, max_depth=12,
                                           n_jobs=-1, random_state=42)),
        ]),
        "svm_rbf": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", C=4.0, gamma="scale", probability=True,
                        random_state=42)),
        ]),
        "mlp": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3,
                                  max_iter=600, early_stopping=True,
                                  random_state=42)),
        ]),
    }
    results = {}
    for name, model in candidates.items():
        t0 = time.time()
        try:
            model.fit(Xtr, ytr)
        except ValueError as error:
            # 训练集只有一个类别等情况：跳过该候选模型
            print(f"[train] {name}: 跳过 ({error})")
            continue
        acc = float((model.predict(Xva) == yva).mean()) if len(Xva) else float("nan")
        results[name] = {"model": model, "val_accuracy": acc, "fit_s": time.time() - t0}
        print(f"[train] {name}: val_acc={acc:.3f} ({time.time()-t0:.1f}s)")
    if not results:
        raise RuntimeError("所有候选模型训练失败（检查标签分布与训练/测试划分）")
    return results


def save_model(path: str | Path, model, n_sc: int, window_cfg: WindowConfig,
               val_accuracy: float, session_names: List[str],
               extra: Optional[dict] = None):
    import joblib
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    meta = {
        "model_file": path.name,
        "n_subcarriers": int(n_sc),
        "window_s": window_cfg.window_s,
        "step_s": window_cfg.step_s,
        "val_accuracy": val_accuracy,
        "feature_names": feature_names(n_sc),
        "sessions": [str(s) for s in session_names],
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "classes": ["idle", "motion"],
        "extra": extra or {},
    }
    path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_model(path: str | Path):
    import joblib
    path = Path(path)
    model = joblib.load(path)
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    return model, meta


def evaluate(model, X: np.ndarray, y: np.ndarray) -> dict:
    """测试集评估：准确率 + 混淆矩阵 + 误报/漏检。"""
    from sklearn.metrics import confusion_matrix
    pred = model.predict(X)
    cm = confusion_matrix(y, pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        "accuracy": float((pred == y).mean()),
        "false_positive_rate": float(fp / max(1, fp + tn)),   # 无人判为有人
        "false_negative_rate": float(fn / max(1, fn + tp)),   # 有人漏检
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
