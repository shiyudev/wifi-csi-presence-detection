# 数据分析（第一次采集）

对 [采集数据](../采集数据/) 的逐段统计与可视化，回答「哪些动作在
哪些子载波上有反应、反应有多强」。

## 文件说明

| 文件 | 内容 |
|---|---|
| `analyze.py` | 逐文件统计：包数、时长、pps、丢包、RSSI、运动指数（motion_idx）、主频率 |
| `summary.json` | 统计结果汇总（每段 24~28 秒、100 pps、0 丢包、RSSI ≈ -46 dBm） |
| `make_figs.py` | 从数据生成 4 张分析图 |
| `build_ppt.js` | 把图表与文字打包成分析报告 pptx |
| `figs/fig1_motion.png` | 各场景运动响应强度对比 |
| `figs/fig2_heatmap.png` | 子载波 × 时间热力图 |
| `figs/fig3_subcarrier.png` | 单个子载波的时域曲线 |
| `figs/fig4_spectrum.png` | 频谱分析（运动信号的频率特征） |
| `dev_mats.npz` / `representative.npz` / `sc_vars.npz` | 分析中间数据 |
| `CSI数据采集分析报告.pptx` | 分析报告成品（精简版；完整版在仓库根目录） |

## 运行

```bash
python analyze.py      # 重新统计 → summary.json
python make_figs.py    # 重新出图 → figs/
```
