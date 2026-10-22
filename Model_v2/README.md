# 首次训练的占用检测模型（v2）

## 这个模型做什么

判断「有效区域内有没有人」（effective zone occupancy）：
- 标签 1 = 区域内有人（玩电脑 / 走动 / 设备旁挥手）
- 标签 0 = 无人（空场 / 仅风扇运行 / 人在门外走动）

> 注意：当前探索模型的任务是「有人 / 无人」，与第一版工具链的
> 「有移动 / 无移动」是两个不同任务，标签不能混用。

## 首次训练结果（开发评测，非最终结论）

| 指标 | 数值 |
|---|---|
| 训练窗口 / 测试窗口 | 82 / 68 |
| 准确率 accuracy | **78%** |
| 平衡准确率 balanced accuracy | **77%**（多数类基线 51%） |
| 漏检（有人判成无人） | 1 例（很少） |
| 误报（无人判成有人） | 14 例（主要误差来源，后续重点优化方向） |

- 训练/测试按**文件**划分（8 个文件训练、6 个文件测试），
  同一段数据不会同时出现在两边，避免虚高
- 完整结果：`results/report.json`（含逐文件明细）、`results/audit.csv`、
  `results/test_predictions.csv`

## 文件说明

| 文件 | 内容 |
|---|---|
| `CSI_Occupancy_v2.ipynb` | 训练全流程 notebook（可逐步复现） |
| `train.py` | 命令行训练脚本 |
| `labels.json` | 每个文件的标签、划分与依据（以文件名为准） |
| `results/occupancy_model.joblib` | 训练好的模型文件 |
| `results/report.json` | 评测报告（准确率、混淆矩阵、逐文件结果） |
| `README_中文.md` | 模型作者写的原始说明 |

## 运行

```bash
pip install -r requirements.txt
python train.py
```
