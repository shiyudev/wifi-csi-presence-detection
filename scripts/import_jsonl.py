#!/usr/bin/env python3
"""把 ESPectre 官方工具导出的 JSONL 会话转成训练用 csi.npz 会话目录。

用法:
    python scripts/import_jsonl.py --src <jsonl目录> --out data/sessions

JSONL 格式: 首行为 metadata（含 action），其余每行一个 CSI 包（i/q 各 64）。
npz 内容与 recorder.record() 一致:
    csi_data: int8 [N, SC*2]，交织顺序 [Q0,I0,Q1,I1,...]（见 protocol.iq_to_amplitude_matrix）
    timestamp: float64 [N]，秒
    label: str，取值须能被 model.label_to_binary 归并
另写 meta.json 保留原始元信息与标签映射说明。

场景 → 标签映射（第一版二分类 motion/idle）:
    空场无人   -> empty  (idle)
    风扇无人   -> fan    (idle)
    走动       -> walk   (motion)
    玩电脑     -> typing (motion)
    设备旁挥手 -> motion
    起身出教室 -> walk   (motion)
    门口走     -> walk   (motion)  # 已知困难样本：远端链路不穿人，信号≈基线
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

LABEL_MAP = {
    "空场无人": "empty",
    "风扇无人": "fan",
    "走动": "walk",
    "玩电脑": "typing",
    "设备旁挥手": "motion",
    "起身出教室": "walk",
    "门口走": "walk",
}


def scene_of(name: str) -> str:
    for scene in LABEL_MAP:
        if name.startswith(scene):
            return scene
    return ""


def convert_file(path: Path, out_dir: Path) -> dict:
    meta, iq_rows, times = None, [], []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            if o.get("type") == "metadata":
                meta = o
                continue
            if o.get("type") != "csi":
                continue
            i = np.asarray(o["i"], dtype=np.int8)
            q = np.asarray(o["q"], dtype=np.int8)
            # 交织为 [Q0,I0,Q1,I1,...]，与协议一致
            iq = np.empty(i.size * 2, dtype=np.int8)
            iq[0::2], iq[1::2] = q, i
            iq_rows.append(iq)
            times.append(o["browser_received_epoch_ms"] / 1000.0)
    if not iq_rows:
        raise ValueError(f"{path.name}: 没有csi包")
    iq_arr = np.stack(iq_rows)
    times = np.asarray(times, dtype=np.float64)
    order = np.argsort(times)  # 防乱序
    times, iq_arr = times[order], iq_arr[order]

    scene = scene_of(path.stem)
    label = LABEL_MAP.get(scene, "")
    if not label:
        raise ValueError(f"{path.name}: 无法映射场景标签")

    sess_dir = out_dir / path.stem
    sess_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(sess_dir / "csi.npz", csi_data=iq_arr,
                        timestamp=times, label=label)
    meta_out = dict(meta or {})
    meta_out.update({"label": label, "scene": scene, "packets": int(len(iq_arr)),
                     "duration_s": round(float(times[-1] - times[0]), 2),
                     "source_file": path.name,
                     "label_note": "门口走为已知困难样本：远端活动链路不穿人，信号≈基线"
                                   if scene == "门口走" else ""})
    (sess_dir / "meta.json").write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"name": path.stem, "scene": scene, "label": label,
            "packets": int(len(iq_arr)),
            "duration_s": round(float(times[-1] - times[0]), 2)}


def main():
    ap = argparse.ArgumentParser(description="JSONL 会话导入为训练格式")
    ap.add_argument("--src", required=True, help="JSONL 所在目录")
    ap.add_argument("--out", default="data/sessions", help="会话输出目录")
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(src.glob("*.jsonl")):
        try:
            rows.append(convert_file(p, out))
            print(f"[import] {p.name} -> ok")
        except Exception as e:  # noqa: BLE001
            print(f"[import] {p.name} -> 失败: {e}")
    print(f"\n[import] 完成 {len(rows)}/{len(list(src.glob('*.jsonl')))} 个会话")
    for r in rows:
        print(f"  {r['name']}: scene={r['scene']} label={r['label']} "
              f"{r['packets']}包 {r['duration_s']}s")
    if len(rows) < 15:
        sys.exit("有会话导入失败，请检查")


if __name__ == "__main__":
    main()
