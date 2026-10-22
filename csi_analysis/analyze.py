# -*- coding: utf-8 -*-
"""CSI 采集数据批量分析：质量指标 + 动态强度 + 子载波敏感性"""
import json, glob, os, math
import numpy as np

SRC = "/home/z/my-project/upload/mount_agent_directory/采集数据"
OUT = "/home/z/my-project/csi_analysis"

VALID = slice(4, 64)          # 剔除前 4 个置零空载波
EMA_A = 0.02                  # 基线 EMA 系数（约1s时间常数 @100pps）

def load_session(path):
    meta, amps, rssis, seqs, ts = None, [], [], [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["type"] == "metadata":
                meta = r
            elif r["type"] == "csi":
                amps.append(r["amplitude"])
                rssis.append(r["rssi_dbm"])
                seqs.append(int(r["sequence"]))
                ts.append(r["browser_received_epoch_ms"])
    return meta, np.array(amps, float), np.array(rssis), np.array(seqs), np.array(ts)

def analyze(path):
    meta, A, rssi, seq, ts = load_session(path)
    t = (ts - ts[0]) / 1000.0
    dur = t[-1] if len(t) > 1 else 0
    pps = len(t) / dur if dur > 0 else 0
    loss = int(np.sum(np.diff(seq) > 1))
    # 每子载波 EMA 基线 → 动态偏差
    base = A[0].copy()
    dev = np.zeros_like(A)
    for k in range(len(A)):
        d = A[k] - base
        dev[k] = d
        base += EMA_A * d
    # 动态强度：偏差 RMS（对时间），再对有效子载波取均值
    motion = float(np.sqrt((dev[:, VALID] ** 2).mean(axis=0)).mean())
    # 子载波敏感度：幅度时间序列方差
    sc_var = A[:, VALID].var(axis=0)
    # 主频分析：先高通去漂移（EMA alpha=0.1），再看 2-48Hz 特征
    k_top = 4 + int(np.argmax(sc_var))
    x = A[:, k_top].copy()
    ema = x[0]
    for k in range(len(x)):
        d = x[k] - ema
        x[k] = d
        ema += 0.1 * d
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 0.01)
    band = (freqs > 2) & (freqs < 48)
    peak_f = float(freqs[band][np.argmax(spec[band])]) if band.any() else 0.0
    peak_p = float(spec[band].max() / (spec[band].sum() + 1e-9)) if band.any() else 0.0
    return {
        "file": os.path.basename(path), "label": meta.get("object", "?"),
        "action": meta.get("action", "?"), "position": meta.get("position", "?"),
        "packets": len(A), "dur_s": round(dur, 1), "pps": round(pps, 1),
        "seq_gaps": loss, "rssi_mean": round(float(rssi.mean()), 1),
        "motion_idx": round(motion, 3),
        "sc_var": sc_var.tolist(), "peak_f": round(peak_f, 2), "peak_ratio": round(peak_p, 3),
        "time": t.tolist(), "dev_energy": np.sqrt((dev[:, VALID] ** 2).mean(axis=1)).tolist(),
    }

def x_mean(x):
    return x - x.mean()

if __name__ == "__main__":
    results = []
    for p in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
        try:
            r = analyze(p)
            results.append(r)
            print(f"{r['file']:<22} {r['label']:<6} {r['packets']:>5}包 {r['dur_s']:>5}s "
                  f"{r['pps']}pps 丢包{r['seq_gaps']} 动态强度{r['motion_idx']:.3f} "
                  f"RSSI{r['rssi_mean']}dBm 主频{r['peak_f']}Hz占比{r['peak_ratio']}")
        except Exception as e:
            print("FAIL", p, e)
    # 保存摘要（不含大数组）
    slim = [{k: v for k, v in r.items() if k not in ("time", "dev_energy", "sc_var")} for r in results]
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=1)
    # 保存逐包数据供热力图（每类取代表会话）
    rep = {}
    for r in results:
        rep.setdefault(r["label"], []).append(r["file"])
    keep = {}
    for r in results:
        lab = r["label"]
        # 每类取包数最多的会话作代表
        if lab not in keep or r["packets"] > keep[lab]["packets"]:
            keep[lab] = r
    # 保存代表会话的完整偏差矩阵（时间×子载波）供热力图
    mats = {}
    for p in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
        fn = os.path.basename(p)
        lab = next(r["label"] for r in results if r["file"] == fn)
        if keep[lab]["file"] != fn:
            continue
        _, A, *_ = load_session(p)
        base = A[0].copy()
        dev = np.zeros_like(A)
        for k in range(len(A)):
            d = A[k] - base
            dev[k] = d
            base += EMA_A * d
        mats[lab] = dev[:, VALID].astype(np.float32)
    np.savez_compressed(os.path.join(OUT, "dev_mats.npz"), **mats)
    # 子载波方差曲线
    np.savez_compressed(os.path.join(OUT, "sc_vars.npz"),
        **{f"{r['file']}": np.array(r["sc_var"]) for r in results})
    print(f"\n完成 {len(results)} 个会话")
