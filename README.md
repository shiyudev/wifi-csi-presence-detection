# WiFi CSI 存在检测（Wi-Fi CSI Presence Detection）

基于 **ESP32-C6 + ESPectre** 固件的 Wi-Fi CSI 人体移动检测项目。
利用 Wi-Fi 信道状态信息（Channel State Information, CSI）实现房间内
「有移动 / 无移动」（motion / idle）的实时判别。

> 本科生软件工程项目 · 第一阶段：真机链路打通 + 数据采集工具链 + 初步实验

## 硬件与网络

| 项目 | 配置 |
|---|---|
| 开发板 | ESP32-C6-DevKitC-1-N8 |
| 固件 | ESPectre Native 3.0.0（csi_profile: ht20，64 子载波） |
| 路由器 | 2.4 GHz（NovaLab-Test，信道 11，WPA2） |
| 电脑端 | Windows / Python 3.10+ |

## 环境安装

```bash
cd csi_project
pip install -r requirements.txt
```

## 快速开始

```bash
# 1. 找到设备（局域网扫描 62587 端口）
python scripts/find_device.py --subnet 192.168.31

# 2. Web 控制台（推荐：实时曲线 / 带标签采集 / 实时检测）
python scripts/webui.py          # 浏览器打开 http://127.0.0.1:8000

# 3. 命令行采集
python scripts/record.py --host <设备IP> --label walk --duration 30 \
    --description "1米往返 正常步速"

# 4. 训练模型
python scripts/train.py --data data --out models/detector.joblib

# 5. 实时检测
python scripts/run_detector.py --host <设备IP> --model models/detector.joblib
```

观察曲线可用官方 visualizer：https://espectre.dev/tools/csi-visualizer/
（与本地工具读同一路 CSI 流）。

> ⚠️ **CSI 流同时只允许一个会话**（固件限制）：
> 官方 visualizer 页面、控制台采集、实时检测三者不要同时开。

## 数据格式

每次采集在 `data/<时间戳>_<标签>/` 下生成一个会话：

- `csi.npz` —— 原始 IQ 数据（ESPectre 兼容格式：csi_data / timestamp / label 等）
- `meta.json` —— 标签、设备信息、包数、平均速率、丢帧统计

标签体系与采集纪律见 [outputs/collection_plan.md](outputs/collection_plan.md)。

## 目录结构

```
espectre_csi/       核心库（协议解析 / 采集 / 特征 / 训练 / 检测 / Web 后端）
  protocol.py         V8 协议解析、HTTP 流客户端、UDP 探测包
  recorder.py         带标签采集会话
  viz.py              命令行实时曲线（原始幅度 + 瀑布图）
  features.py         滑动窗口特征
  model.py            训练 / 评估 / 保存
  detector.py         实时检测与预测日志
  webapp.py           Web 控制台后端（Flask + SSE）
  dashboard.html      Web 控制台前端（Canvas 渲染）
scripts/            命令行工具（find_device / live_view / record / train /
                    run_detector / webui / sim_device）
data/               采集数据（会话目录）
models/             训练好的模型
outputs/            预测日志、实验记录（观察表 / 采集方案 / 初步结果）
docs/               ESPectre 官方协议文档与本工具链核对记录
tests/              端到端测试（模拟器全流程验证）
```

## 本仓库相对上游工具链的修复

真实设备（固件 3.0.0）验证中发现并修复：

1. **Origin 头**：固件 3.0.0 所有 HTTP 端点要求 `Origin: https://espectre.dev`，
   否则返回 403（`protocol.py` / `find_device.py`）
2. **断流自动重连**：CSI 流中断（IncompleteRead）时自动重连，
   实时可视化不再崩溃（`CSIStreamClient.packets(retry=True)`）
3. **wait_ready 兼容**：兼容 3.0.0 无 `state` 字段的 `/sensing` 响应，
   并把等待超时从 45s 缩短为 5s（外部流量模式不依赖设备端检测器就绪）
4. **特征除零保护**：真实设备存在恒定子载波，`corrcoef` 除零产生
   NaN 与警告刷屏，已改为只对非常数列求相关（`features.py`）
5. **Web 检测线程生命周期**：停止检测时 join 全部线程并释放 CSI 流，
   修复「幽灵检测线程占流导致采集 409」问题（`webapp.py`）

## 实验进度

- ✅ 真机链路验证：100 pps、0 丢帧、0 解析错误
- ✅ 端到端流水线冒烟测试（模拟器）：随机森林 / SVM 验证准确率 100%
- ✅ 第一段真实数据采集（30s empty，2991 包）
- ✅ 真机实时检测试运行（10 分钟预测日志，motion/idle 切换与人员活动吻合）
- ⏳ 观察实验（动作 × 距离 响应强度记录）
- ⏳ 正式规范采集（见 collection_plan.md）→ 真数据训练 → 评测报告

详细结果见 [outputs/PRELIMINARY_RESULTS.md](outputs/PRELIMINARY_RESULTS.md)。

## 协议参考

- ESPectre: https://github.com/francescopace/espectre
- 协议细节与固件源码核对记录见 `docs/`
