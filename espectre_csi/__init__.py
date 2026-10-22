"""ESPectre CSI 采集工具链。

基于 ESPectre 固件 (https://github.com/francescopace/espectre) 的
Direct HTTP 原始 CSI 接口，提供：
- 原始 CSI 流接收与 V8 记录解析 (protocol)
- 带标签的实验数据采集与保存 (recorder)
- 实时子载波曲线可视化 (viz)
- 滑动窗口特征提取与模型训练 (features / model)
- 实时有人/移动检测与预测日志 (detector)
"""

__version__ = "0.1.0"
