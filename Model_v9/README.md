# CSI V9：1–5号合并训练版

已使用11月3日四种情况各1–5号、共20份原始JSONL重新拟合。四份5号此前用于V8测试，本版已按用户要求转入训练集。V9尚无独立测试准确率。

## 本次新增

| 文件 | 新增两秒训练窗口 |
|---|---:|
| 无人5 | 17 |
| 门外走动5 | 17 |
| 玩电脑5 | 15 |
| 走动5 | 13 |
| 合计 | 62 |

总计345个窗口、690秒，其中有人203个，无人142个。原1–4号的283个窗口、标签和数值特征保持不变。仅使用今天这批数据，没有混入以前房间的数据。

无人、门外走动文件均按“出门=有人、中段=屋内无人、进门=有人”分段。蓝线附近7个窗口和5号视频未完整覆盖的3个窗口排除。视频与CSI从头对齐；5号视频此前每3秒抽帧核对，并非逐帧验证。原1–4号按V8标注保留，包括以用户文件名场景作为依据的视频尾段；逐窗口证据覆盖情况见审计表。

无人5约15.509秒的单帧尖峰保留在原始数值中，所属窗口标为无人。原始记录未修改，未针对测试结果清除尖峰。

## 使用已训练模型

解压到新文件夹，在含有 `predict.py` 的目录打开PowerShell。不要覆盖V8文件夹。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe verify.py
```

将新采集的JSONL放进此目录，把下方“新数据.jsonl”替换为实际文件名：

```powershell
.\.venv\Scripts\python.exe predict.py "新数据.jsonl" --candidate all --out "test_results\新数据.csv"
```

只运行默认方法可以省略 `--candidate all`。输出路径不能已存在。程序不会从预测中自动学习。不提供 `--truth` 时，正误栏留空；包含进出门的文件不能整段指定 `--truth 0`。

若重测这四份5号，摘要会显示 `seen_in_training: true` 和 `evaluation_role: training_diagnostic`；改文件名前缀也不会变成独立测试。新一轮效果需另外采集数据核对。

## 模型设置

沿用V8特征和参数：随机森林200棵树、最大深度5、叶节点最少3、类别平衡、种子42。使用全部20份数据重新拟合；没有只用5号覆盖原模型，也没有将CSV预测作为训练标签。

保留3个森林、4种规则：默认 `v6_rf` 阈值0.5；`rf_threshold_060` 阈值0.6；`common_rf` 和 `common_median_rf` 阈值0.5。未按5号结果更换默认方法或搜索参数。`v6_rf` 是特征方法名，本包模型版本为 `9.0-nov03-train15`。

照片、画线图和视频用于场景及标签核对；训练数值来自原始CSI。

## 可复现与历史记录

- `results/occupancy_model_v9.joblib`：已训练模型，可直接预测。
- `labels_train.json`：20份文件的训练标签区间。
- `results/training_report.json`：实际训练统计。
- `results/window_audit.csv`：全部窗口、排除原因和视频覆盖状态。
- `results/verification.json`：模型重新载入和原283个窗口一致性检查。
- `history/CSI_Training_v8_Train14.zip`：原V8完整包，保持原字节不变。
- `history/v8_test_results/`：用户上传的四份V8预测CSV，保持原字节不变。
- `history/v8_holdout_summary.json`、`v8_scored_windows.csv`：V8历史核对结果。默认方法60/62；这些数字仅属于V8。

如需重训，将原始两份ZIP放进当前目录；程序输出必须使用新目录：

```powershell
.\.venv\Scripts\python.exe -m unittest test_v9 -v
.\.venv\Scripts\python.exe train.py --zip "11.3日数据1含画线.zip" --zip "11.3日数据2.zip" --out results_retrained
.\.venv\Scripts\python.exe verify.py --results results_retrained
```

训练入口会核对源文件和原始ZIP的SHA256。原始CSI和视频不重复打包，仍使用用户原压缩包。推理不需要原始训练ZIP。

本版完成程序测试、保存读取一致性检查及四份原5号的预测入口检查。未在用户Windows电脑上实际执行；尚未接入实时ESP32数据流。新版本的泛化效果待独立数据验证。
