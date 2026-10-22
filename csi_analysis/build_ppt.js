const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.33, height: 7.5 });
p.layout = "W";

// ── 视觉系统 ──
const BG = "FFFFFF", DARK = "0F1B2D", DARK2 = "16263D", TEXT = "1E2A3A",
      MUTED = "7A8699", ACCENT = "4C6EF5", TINT = "EEF2FB", LINE = "D9E0EA";
const F = "微软雅黑";
const W = 13.33, H = 7.5, M = 0.6;
const FIG = "/home/z/my-project/csi_analysis/figs/";

const t = (s, o) => ({ text: s, options: Object.assign({ fontFace: F, color: TEXT }, o || {}) });

// 封面/封底深色页装饰：右下角同心波纹（WiFi 意象）
function rings(s, cx, cy, base, n, colr) {
  for (let i = 0; i < n; i++) {
    const d = base + i * 0.75;
    s.addShape("ellipse", { x: cx - d / 2, y: cy - d / 2, w: d, h: d,
      fill: { type: "none" }, line: { color: colr, width: 1.2, transparency: 25 + i * 14 } });
  }
}

// ═══ 1 封面 ═══
{
  const s = p.addSlide();
  s.background = { color: DARK };
  rings(s, 12.4, 1.1, 0.9, 4, ACCENT);
  rings(s, 0.7, 6.9, 0.6, 3, "3AAFA9");
  s.addText([t("Wi-Fi CSI 人员存在检测", { fontSize: 20, color: "8FA8CC", charSpacing: 4, breakLine: true }),
             t("首批真实数据采集与分析报告", { fontSize: 44, bold: true, color: "FFFFFF", breakLine: true })],
    { x: 0.9, y: 2.3, w: 11.5, h: 2.1, lineSpacingMultiple: 1.25 });
  s.addText([t("7 类场景 · 15 次会话 · 36,117 个 CSI 数据包 · 零丢包", { fontSize: 16, color: ACCENT, breakLine: true }),
             t("ESPectre V8 真实 CSI  |  教室 6B514  |  2026-10-20", { fontSize: 13, color: MUTED })],
    { x: 0.9, y: 4.5, w: 11, h: 1.0, lineSpacingMultiple: 1.6 });
}

// ═══ 2 核心结论 ═══
{
  const s = p.addSlide();
  s.background = { color: BG };
  s.addText([t("核心结论", { fontSize: 30, bold: true })], { x: M, y: 0.45, w: 6, h: 0.6 });
  s.addText([t("15 次会话的数据质量与特征区分度均达到训练标准，同时暴露出一个覆盖盲区",
    { fontSize: 15, color: MUTED })], { x: M, y: 1.1, w: 11, h: 0.4 });
  const rows = [
    ["01", "信号对人的响应清晰可辨", "走动使子载波动态达到空场基线的 3~4 倍（2.4~3.2 vs 0.82）；起身、挥手等动作均显著越线，有人/无人的一级判别在幅度层面即已可分。", ACCENT],
    ["02", "不同干扰源有可分辨的指纹", "风扇无人仅使动态升至 1.0 左右，且在频谱上留下稳定的 6.6 Hz 周期峰，与人体动作频段（2~4 Hz）完全分离——风扇误报可用滤波排除。", "C9A227"],
    ["03", "感知范围存在边界", "门口走动（远端）动态仅 0.82，与空场基线持平；久坐玩电脑单次会话可低至 0.70。设备朝向与链路覆盖是下一阶段必须补测的变量。", "C0392B"],
  ];
  let y = 1.75;
  for (const [no, h1, d, c] of rows) {
    s.addText([t(no, { fontSize: 30, bold: true, color: c })], { x: M, y: y, w: 0.8, h: 0.7 });
    s.addText([t(h1, { fontSize: 17.5, bold: true, breakLine: true }),
               t(d, { fontSize: 12.5, color: MUTED })],
      { x: 1.55, y: y, w: 11.2, h: 1.5, lineSpacingMultiple: 1.28, valign: "top" });
    if (no !== "03") s.addShape("line", { x: 1.55, y: y + 1.52, w: 11.15, h: 0, line: { color: LINE, width: 0.75 } });
    y += 1.78;
  }
}

// ═══ 3 采集概况 ═══
{
  const s = p.addSlide();
  s.background = { color: BG };
  s.addText([t("采集概况", { fontSize: 30, bold: true })], { x: M, y: 0.45, w: 5, h: 0.6 });
  s.addText([t("数据来自 espectre.dev 官方工具直连设备，每包含 64 子载波 I/Q、RSSI、SNR 与原始 V8 帧",
    { fontSize: 14, color: MUTED })], { x: M, y: 1.1, w: 12, h: 0.4 });
  // 左：场景表
  const head = ["场景", "会话数", "总时长", "动态强度均值"];
  const body = [
    ["空场无人", "2", "49.0 s", "0.82"],
    ["风扇无人", "3", "72.3 s", "1.02"],
    ["玩电脑", "3", "77.7 s", "1.15"],
    ["设备旁挥手", "2", "48.1 s", "2.24"],
    ["起身出教室", "1", "18.9 s", "2.48"],
    ["门口走", "1", "23.9 s", "0.82"],
    ["走动", "3", "72.9 s", "2.76"],
  ];
  const rowsT = [head.map(h => t(h, { fontSize: 12.5, bold: true, color: MUTED }))]
    .concat(body.map((r, i) => r.map((c, j) => t(c, {
      fontSize: 12.5, bold: j === 0,
      color: j === 3 ? (parseFloat(c) > 2 ? ACCENT : TEXT) : TEXT }))));
  s.addTable(rowsT, { x: M, y: 1.75, w: 6.3, rowH: 0.42, fontFace: F,
    border: { type: "solid", color: LINE, pt: 0.5 }, valign: "middle",
    fill: { color: "FFFFFF" }, margin: 0.06 });
  // 右：质量大数字
  const stats = [["100", "pps 恒定采样率", "15 次会话无一波动"], ["0", "丢包 / 序号缺口", "36,117 包全部连续"], ["-47.9", "dBm 平均 RSSI", "链路稳定，SNR 余量充足"]];
  let y = 1.8;
  for (const [n, l, d] of stats) {
    s.addShape("roundRect", { x: 7.3, y: y, w: 5.4, h: 1.45, rectRadius: 0.08, fill: { color: TINT } });
    s.addText([t(n, { fontSize: 40, bold: true, color: ACCENT, breakLine: true }),
               t(l + "  ·  " + d, { fontSize: 12.5, color: MUTED })],
      { x: 7.7, y: y + 0.12, w: 4.8, h: 1.2, lineSpacingMultiple: 1.1, valign: "middle" });
    y += 1.68;
  }
  s.addText([t("注：前 4 个子载波为协议置零空载波，全部分析已剔除；动态强度 = 子载波幅度相对滑动基线的 RMS 偏差。",
    { fontSize: 10.5, color: MUTED, italic: true })], { x: M, y: 6.85, w: 12.2, h: 0.35 });
}

// ═══ 4-7 图表页（通用版式：左图右评） ═══
function chartSlide(no, title, sub, img, aspect, takeaways, srcNote) {
  const s = p.addSlide();
  s.background = { color: BG };
  s.addText([t(`${no}  `, { fontSize: 22, bold: true, color: ACCENT }),
             t(title, { fontSize: 25, bold: true })], { x: M, y: 0.4, w: 12, h: 0.55 });
  s.addText([t(sub, { fontSize: 12.5, color: MUTED })], { x: M, y: 1.02, w: 12, h: 0.35 });
  const iw = 8.75, ih = iw / aspect;
  s.addImage({ path: img, x: M, y: 1.55, w: iw, h: ih });
  const step = takeaways.length > 3 ? 1.32 : 1.62;
  const bh = takeaways.length > 3 ? 1.24 : 1.55;
  let y = 1.62;
  for (const [h1, d] of takeaways) {
    s.addText([t(h1, { fontSize: 14, bold: true, breakLine: true }),
               t(d, { fontSize: 11.5, color: MUTED })],
      { x: 9.65, y: y, w: 3.1, h: bh, lineSpacingMultiple: 1.22, valign: "top" });
    y += step;
  }
  s.addShape("line", { x: 9.65, y: 1.5, w: 0, h: 5.3, line: { color: LINE, width: 0.75 } });
  s.addText([t(srcNote, { fontSize: 10, color: MUTED, italic: true })],
    { x: M, y: 6.95, w: 9, h: 0.3 });
  return s;
}

chartSlide("4", "动态强度：人体活动显著抬升信号", "每根柱为一次会话；虚线为两次空场会话的基线均值",
  FIG + "fig1_motion.png", 1.946,
  [["走动是最强激励", "三次会话稳定在 2.39~3.18，为基线的 3~4 倍，会话间一致性良好。"],
   ["近场小动作可辨", "设备旁挥手 1.70~2.79、起身 2.48，均明显越过基线。"],
   ["玩电脑方差大", "0.70~1.66：久坐身体遮挡反而压低波动，单次低于基线。"]],
  "数据：本次 15 次会话 · 指标为有效子载波（4~63）偏差 RMS 的均值");

chartSlide("5", "时序形态：四种场景肉眼可分", "横轴时间 · 纵轴子载波 · 颜色为幅度偏差（红正蓝负）",
  FIG + "fig2_heatmap.png", 1.773,
  [["空场", "均匀细噪，无结构。"], ["风扇", "少数子载波出现周期性细条。"], ["玩电脑", "间歇性局部扰动。"], ["走动", "连片强波动，跨子载波相关。"]],
  "展示的 4 个会话为各类包数最多的代表；中央白色行为协议直流空载波");

chartSlide("6", "子载波敏感性分布", "纵轴为幅度方差（对时间），各场景按会话取均值",
  FIG + "fig3_subcarrier.png", 2.016,
  [["中段是黄金区间", "走动时 12~16 号子载波方差达峰值，约为空场的 8 倍。"],
   ["区分度全带存在", "走动曲线全程高于其他场景，但低号段（4~10）与风扇有交叠。"],
   ["对训练的意义", "特征可先用 top 方差子载波降维；30/59 号后的塌陷区应剔除。"]],
  "空场/风扇/玩电脑/走动 4 类均值曲线，走动加粗突出");

chartSlide("7", "频谱指纹：风扇可被滤波排除", "对各类最敏感的 5 个子载波取平均功率谱（1~48 Hz，已去低频漂移）",
  FIG + "fig4_spectrum.png", 2.016,
  [["6.6 Hz 稳定复现", "风扇三次采集主频分别为 6.75 / 6.57 / 6.45 Hz，高度一致。"],
   ["与人体频段分离", "人体动作能量集中在 2~4 Hz，频域上与风扇不重叠。"],
   ["落地做法", "检测前对 5.5~8 Hz 窄带陷波，可低成本消除风扇误报。"]],
  "走动谱在低频段能量分散且强；空场全带平坦");

// ═══ 8 风险发现 ═══
{
  const s = p.addSlide();
  s.background = { color: BG };
  s.addText([t("两个需要正视的问题", { fontSize: 30, bold: true })], { x: M, y: 0.45, w: 8, h: 0.6 });
  s.addText([t("它们不否定方案可行性，但直接决定下一批采集怎么设计", { fontSize: 14, color: MUTED })],
    { x: M, y: 1.1, w: 11, h: 0.4 });
  const cards = [
    ["感知盲区：门口走动完全隐身", "C0392B",
     "门口走会话动态强度 0.82，与空场基线完全重合——人在房间远端活动时，链路（设备↔路由器）没有穿过其身体。",
     ["人体对信号的调制依赖「穿越链路」，覆盖是几何问题而非算法问题",
      "对策：调整设备朝向 / 增加第二链路；下批采集按距链路 0/2/4/6 m 分档补测"]],
    ["久坐场景与空场难以区分", "C9A227",
     "玩电脑三次会话强度 0.70 / 1.66 / 1.08，方差大且最低值低于基线——存在检测在「人在但静止」时可能漏报。",
     ["久坐时唯一信号是呼吸/微动，幅度层面可能确实不足",
      "对策：降低判定阈值会牺牲鲁棒性，建议引入微动特征（呼吸频段 0.2~0.5 Hz）单独验证"]],
  ];
  let x = M;
  for (const [h1, c, d, pts] of cards) {
    s.addShape("roundRect", { x: x, y: 1.75, w: 5.95, h: 4.9, rectRadius: 0.09, fill: { color: TINT } });
    s.addText([t(h1, { fontSize: 17, bold: true, color: c, breakLine: true }),
               t(d, { fontSize: 12.5, color: TEXT, breakLine: true })],
      { x: x + 0.35, y: 2.05, w: 5.25, h: 2.0, lineSpacingMultiple: 1.3, valign: "top" });
    s.addText(pts.map((pt, i) => t(pt, { fontSize: 12, color: MUTED, bullet: { code: "2022", indent: 12 },
      breakLine: i < pts.length - 1, paraSpaceAfter: 10 })),
      { x: x + 0.35, y: 4.15, w: 5.25, h: 2.3, lineSpacingMultiple: 1.25, valign: "top" });
    x += 6.2;
  }
}

// ═══ 9 结论与下一步 ═══
{
  const s = p.addSlide();
  s.background = { color: DARK };
  rings(s, 12.6, 6.6, 0.8, 3, ACCENT);
  s.addText([t("结论与下一步", { fontSize: 30, bold: true, color: "FFFFFF" })], { x: M, y: 0.5, w: 8, h: 0.6 });
  s.addText([t("数据合格，方案可行。", { fontSize: 24, bold: true, color: ACCENT, breakLine: true }),
             t("首批数据已验证：有人/无人判别、风扇干扰排除、敏感子载波选择三个环节都有明确的数据支撑。",
               { fontSize: 14, color: "B8C6DC" })],
    { x: M, y: 1.5, w: 11.5, h: 1.4, lineSpacingMultiple: 1.4 });
  const steps = [
    ["①", "补采盲区数据", "设备朝向调整后，按距链路 0/2/4/6 m 分档走动采集"],
    ["②", "跑通训练管线", "15 会话导入 csi_project 控制台，训练第一版检测模型"],
    ["③", "验证风扇滤波", "加入 6.6 Hz 陷波，对比开启前后误报率"],
    ["④", "扩场景复测", "空场/走动各扩到 5 次以上，覆盖不同时段与家具状态"],
  ];
  let x = M;
  for (const [no, h1, d] of steps) {
    s.addShape("roundRect", { x: x, y: 3.4, w: 2.85, h: 2.5, rectRadius: 0.09, fill: { color: DARK2 } });
    s.addText([t(no + " " + h1, { fontSize: 15.5, bold: true, color: "FFFFFF", breakLine: true }),
               t(d, { fontSize: 11.5, color: "8FA8CC" })],
      { x: x + 0.25, y: 3.65, w: 2.35, h: 2.0, lineSpacingMultiple: 1.3, valign: "top" });
    x += 3.08;
  }
  s.addText([t("数据来源：本次 15 次会话采集 · 分析脚本与中间数据已归档至 csi_analysis 目录",
    { fontSize: 10.5, color: MUTED })], { x: M, y: 6.7, w: 12, h: 0.35 });
}

p.writeFile({ fileName: "/home/z/my-project/csi_analysis/CSI数据采集分析报告.pptx" })
  .then(() => console.log("PPT done"));
