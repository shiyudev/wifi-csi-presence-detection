/* =========================================================
   CSI Occupancy Lab — 二分类实验台
   ---------------------------------------------------------
   两条数据线：
   1) 评估线：使用 results/ 下的真实测试窗口（68 个），
      交互式重算混淆矩阵与指标；
   2) 实时线：前端模拟 CSI 流，仅用于验证交互与展示形态。
   两条线在界面上明确区分，避免把模拟结果当模型效果。
   ========================================================= */
(function () {
  'use strict';

  // 数据集在 initData() 中装载：默认取内嵌 data.js，也可用 ?data=xxx.json 覆盖
  let DATA = null;
  let WINDOWS = [];      // 测试窗口 [{f, s, e, y, sc}]
  let META = null;       // 数据集 / 模型 / 指标元信息
  let CURVE = [];        // 阈值曲线缓存

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const nowMs = () => performance.now();
  const pct = (v, d = 1) => (v * 100).toFixed(d) + '%';
  const pad2 = (n) => String(n).padStart(2, '0');

  // report.json 里的英文局限 → 中文（前缀命中则替换，未命中保留原文）
  const LIMIT_ZH = [
    ['Labels assigned from user-confirmed filenames',
      '标签来自用户确认的文件名与场景上下文，状态切换时刻未经同步视频核验。'],
    ['Only one device, room and collection day',
      '只有一台设备、一个房间、一个采集日；空场录制仅 2 段。'],
    ['Target is occupancy within the designated effective zone',
      '目标是「有效检测区域」内是否有人，不是整间教室。仅风扇运转与门外走廊经过都算无人；尚无经过验证的长时静止/睡眠人员样本。'],
    ['This batch was previously inspected',
      '该批次此前已被查看与评估，留出集结果属于开发证据，不是新的盲测；有效区边界坐标仍未测定。'],
    ['Occupancy score is not a calibrated probability',
      '占据分数不是校准概率。架构与超参数沿用上一版，未在该评估集上调参。']
  ];

  /* =========================================================
     一、状态
     ========================================================= */
  const DEFAULT = {
    threshold: 0.5,
    minDwell: 1.0,
    smoothAlpha: 0.35,
    autoInterval: 12
  };

  const state = {
    // 运行参数
    threshold: DEFAULT.threshold,
    minDwell: DEFAULT.minDwell,
    smoothAlpha: DEFAULT.smoothAlpha,
    autoInterval: DEFAULT.autoInterval,
    auto: true,
    scene: 'vacant',
    source: 'demo',       // 'demo' = 前端模拟流；'replay' = 采集原始帧 + 浏览器内模型推理
    deadSc: [],           // 空载波（直流/保护带）：真实采集中幅度恒为 0
    scUser: false,        // 用户是否手动选过子载波
    scSig: '',            // 空载波集合签名，用于避免重复重建下拉框

    // 分数与判定
    rawScore: 0.14,
    score: 0.14,
    truth: false,
    occupied: false,
    candidate: false,
    candidateSince: nowMs(),
    lastSwitch: nowMs(),
    runStart: nowMs(),
    switches: 0,
    miss: 0,
    fp: 0,

    // 数据缓冲
    frames: [],
    history: [],
    timeline: [],
    lastSecond: -1,
    lastScoreAt: 0,
    lastEventKey: '',
    lastEventAt: 0,
    events: [],
    subcarrier: 32,
    external: false,
    externalScore: 0,
    externalAt: 0,

    // 评估
    evalThreshold: 0.5
  };

  const MAX_FRAMES = 100;      // 5 s @ 50 ms
  const TICK_MS = 50;

  /* =========================================================
     二、真实评估数据与指标
     ========================================================= */
  // WINDOWS / META 由 normalizeMeta() 与 initData() 赋值，见「十四、数据装载」

  function metricsAt(th) {
    let tp = 0, tn = 0, fp = 0, fn = 0;
    for (let i = 0; i < WINDOWS.length; i++) {
      const w = WINDOWS[i];
      const p = w.sc >= th ? 1 : 0;
      if (w.y === 1 && p === 1) tp++;
      else if (w.y === 0 && p === 0) tn++;
      else if (w.y === 0 && p === 1) fp++;
      else fn++;
    }
    const n = WINDOWS.length;
    const acc = (tp + tn) / n;
    const sens = tp + fn ? tp / (tp + fn) : 0;
    const spec = tn + fp ? tn / (tn + fp) : 0;
    const prec = tp + fp ? tp / (tp + fp) : 0;
    const f1 = prec + sens ? (2 * prec * sens) / (prec + sens) : 0;
    return {
      tp, tn, fp, fn, acc,
      bal: (sens + spec) / 2,
      sens, spec, prec, f1,
      n
    };
  }

  // 阈值曲线缓存（5% → 95%），数据装载后重建
  function buildCurve() {
    CURVE = [];
    for (let v = 5; v <= 95; v++) {
      const th = v / 100;
      CURVE.push({ th, ...metricsAt(th) });
    }
  }

  /* =========================================================
     三、模拟 CSI 流
     ========================================================= */

  // 每个场景对应：真值、振幅形态、分数基线
  const SCENES = {
    vacant: { cn: '无人房间', truth: 0, noise: 0.13, lowHz: 0.0, lowAmp: 0.0, hiHz: 0.0, hiAmp: 0.0, spike: 0, base: 0.15, jitter: 0.045 },
    sitting: { cn: '有人 · 静坐', truth: 1, noise: 0.16, lowHz: 0.33, lowAmp: 0.26, hiHz: 1.4, hiAmp: 0.04, spike: 0, base: 0.64, jitter: 0.045 },
    walking: { cn: '有人 · 走动', truth: 1, noise: 0.18, lowHz: 0.47, lowAmp: 1.22, hiHz: 0.0, hiAmp: 0.0, spike: 0, base: 0.87, jitter: 0.04 },
    waving: { cn: '有人 · 挥手', truth: 1, noise: 0.18, lowHz: 0.22, lowAmp: 0.38, hiHz: 0.0, hiAmp: 0.0, spike: 1, base: 0.83, jitter: 0.07 },
    fan: { cn: '风扇干扰', truth: 0, noise: 0.15, lowHz: 0.62, lowAmp: 0.34, hiHz: 0.0, hiAmp: 0.0, spike: 0, base: 0.49, jitter: 0.1 },
    door: { cn: '门口经过', truth: 0, noise: 0.16, lowHz: 0.55, lowAmp: 0.7, hiHz: 0.0, hiAmp: 0.0, spike: 0, base: 0.33, jitter: 0.09 }
  };

  let SC = 64;                 // 子载波数，随数据集元信息变化
  const BASE_AMP = 22;
  let SC_PROFILE = [];

  function buildProfile() {
    SC_PROFILE = Array.from({ length: SC }, (_, i) =>
      1.7 * Math.sin((i / SC) * Math.PI * 2) + 0.75 * Math.sin((i / SC) * Math.PI * 4.4 + 1.1)
    );
  }

  let clockT = 0;

  function genFrame(scene, t) {
    const p = SCENES[scene] || SCENES.vacant;
    const arr = new Float32Array(SC);
    const phase = Math.random() * Math.PI * 2;
    const isSpike = scene === 'waving' && (t % 4.0) < 0.42;

    for (let i = 0; i < SC; i++) {
      let v = BASE_AMP + SC_PROFILE[i] * 0.5;
      v += Math.sin(i * 0.7 + t * 0.08) * 0.16;

      if (p.lowAmp > 0) v += Math.sin(2 * Math.PI * p.lowHz * t + i * 0.13 + phase) * p.lowAmp;
      if (p.hiAmp > 0) {
        v += (Math.random() * 2 - 1) * p.hiAmp;
        v += Math.sin(2 * Math.PI * p.hiHz * t + i * 0.05) * p.hiAmp * 0.6;
      }
      if (isSpike) v += (Math.random() * 2 - 1) * 2.3 * Math.exp(-Math.pow((i - 32) / 13, 2));
      v += (Math.random() * 2 - 1) * p.noise;
      arr[i] = Math.max(0, v);
    }
    return arr;
  }

  // 从窗口帧里算三个可展示的特征，保证界面数字不是凭空写的
  function windowFeatures(frames) {
    const n = frames.length;
    if (!n) return { std: 0, diff: 0, jump: 0, amp: 0 };
    let stdSum = 0, ampSum = 0;
    for (let i = 0; i < SC; i++) {
      let m = 0;
      for (let k = 0; k < n; k++) m += frames[k][i];
      m /= n;
      let v = 0;
      for (let k = 0; k < n; k++) v += (frames[k][i] - m) ** 2;
      stdSum += Math.sqrt(v / n);
      ampSum += m;
    }
    let diffE = 0, maxJump = 0;
    for (let k = 1; k < n; k++) {
      let s = 0;
      for (let i = 0; i < SC; i++) s += Math.abs(frames[k][i] - frames[k - 1][i]);
      s /= SC;
      diffE += s;
      if (s > maxJump) maxJump = s;
    }
    diffE = n > 1 ? diffE / (n - 1) : 0;
    return { std: stdSum / SC, diff: diffE, jump: maxJump, amp: ampSum / SC };
  }

  // 场景 → 原始分数。加入极低频漂移，避免分数是一条死直线。
  function sceneScore(scene, t) {
    const p = SCENES[scene] || SCENES.vacant;
    const drift = Math.sin(2 * Math.PI * 0.11 * t) * 0.035;
    const gauss = (Math.random() + Math.random() + Math.random() - 1.5) * p.jitter;
    let s = p.base + drift + gauss;
    if (scene === 'vacant' && Math.random() < 0.012) s += 0.16; // 偶发空场噪声
    if (scene === 'fan') s += Math.sin(2 * Math.PI * 0.7 * t) * 0.05;
    return clamp(s, 0.02, 0.985);
  }

  /* =========================================================
     四、Canvas 基础
     ========================================================= */
  function fit(cv) {
    const dpr = window.devicePixelRatio || 1;
    const r = cv.getBoundingClientRect();
    const w = r.width, h = r.height;
    if (w < 2 || h < 2) return null;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }

  // 强度色阶（与 CSS 中的 ramp-legend 一致）
  const RAMPS = [
    [7, 10, 24], [30, 58, 138], [14, 165, 233],
    [34, 211, 238], [163, 230, 53], [251, 191, 36], [251, 113, 133]
  ];
  const LUT = (() => {
    const out = [];
    const n = 256;
    for (let i = 0; i < n; i++) {
      const t = (i / (n - 1)) * (RAMPS.length - 1);
      const a = Math.min(Math.floor(t), RAMPS.length - 2);
      const f = t - a;
      out.push([
        Math.round(RAMPS[a][0] + (RAMPS[a + 1][0] - RAMPS[a][0]) * f),
        Math.round(RAMPS[a][1] + (RAMPS[a + 1][1] - RAMPS[a][1]) * f),
        Math.round(RAMPS[a][2] + (RAMPS[a + 1][2] - RAMPS[a][2]) * f)
      ]);
    }
    return out;
  })();

  const heatBuf = document.createElement('canvas');
  heatBuf.width = MAX_FRAMES;
  heatBuf.height = SC;
  const heatBufCtx = heatBuf.getContext('2d');
  const heatImg = heatBufCtx.createImageData(MAX_FRAMES, SC);

  /* =========================================================
     五、绘制：热力图 / 子载波 / 判定流
     ========================================================= */
  function drawHeat() {
    const cv = $('#heatCanvas');
    if (!cv) return;
    const box = fit(cv);
    if (!box) return;
    const { ctx, w, h } = box;

    const n = state.frames.length;
    if (!n) return;

    // 全窗口自适应的显示范围
    let lo = Infinity, hi = -Infinity;
    for (let k = 0; k < n; k++) {
      const f = state.frames[k];
      for (let i = 0; i < SC; i++) {
        const v = f[i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (hi - lo < 0.6) { hi = lo + 0.6; }

    const d = heatImg.data;
    for (let k = 0; k < n; k++) {
      const f = state.frames[k];
      for (let i = 0; i < SC; i++) {
        let t = (f[i] - lo) / (hi - lo);
        t = clamp(t, 0, 1);
        const c = LUT[(t * 255) | 0];
        const idx = (i * MAX_FRAMES + k) * 4;
        d[idx] = c[0];
        d[idx + 1] = c[1];
        d[idx + 2] = c[2];
        d[idx + 3] = 255;
      }
    }
    // 未使用的列填成底色
    for (let k = n; k < MAX_FRAMES; k++) {
      for (let i = 0; i < SC; i++) {
        const idx = (i * MAX_FRAMES + k) * 4;
        d[idx] = 7; d[idx + 1] = 10; d[idx + 2] = 24; d[idx + 3] = 255;
      }
    }
    heatBufCtx.putImageData(heatImg, 0, 0);

    ctx.imageSmoothingEnabled = false;
    const targetW = w * (n / MAX_FRAMES);
    ctx.drawImage(heatBuf, 0, 0, n, SC, w - targetW, 0, targetW, h);

    // 轻微顶/底暗角，压住边缘
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, 'rgba(5,7,14,.35)');
    g.addColorStop(.16, 'rgba(5,7,14,0)');
    g.addColorStop(.84, 'rgba(5,7,14,0)');
    g.addColorStop(1, 'rgba(5,7,14,.35)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  function drawLine() {
    const cv = $('#lineCanvas');
    if (!cv) return;
    const box = fit(cv);
    if (!box) return;
    const { ctx, w, h } = box;

    const n = state.frames.length;
    if (n < 2) return;

    const sc = state.subcarrier;
    const vals = new Array(n);
    let lo = Infinity, hi = -Infinity;
    for (let k = 0; k < n; k++) {
      const v = state.frames[k][sc];
      vals[k] = v;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (hi - lo < 0.4) { hi += 0.2; lo -= 0.2; }
    if (!(hi - lo > 0)) { hi = lo + 1; lo -= 1; }   // 空载波/常量段兜底，避免除零
    const pad = (hi - lo) * 0.14;
    lo -= pad; hi += pad;

    // 网格
    ctx.strokeStyle = 'rgba(126,156,210,.1)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 3; i++) {
      const y = (h / 3) * i;
      ctx.beginPath();
      ctx.moveTo(0, y + .5);
      ctx.lineTo(w, y + .5);
      ctx.stroke();
    }

    const xOf = (k) => (k / (MAX_FRAMES - 1)) * w;
    const yOf = (v) => h - ((v - lo) / (hi - lo)) * h;

    // 面积
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(34,211,238,.22)');
    grad.addColorStop(1, 'rgba(34,211,238,0)');
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    for (let k = 1; k < n; k++) ctx.lineTo(xOf(k), yOf(vals[k]));
    ctx.lineTo(xOf(n - 1), h);
    ctx.lineTo(xOf(0), h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 折线
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    for (let k = 1; k < n; k++) ctx.lineTo(xOf(k), yOf(vals[k]));
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 1.4;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // 最新值
    const lx = xOf(n - 1), ly = yOf(vals[n - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 2.6, 0, Math.PI * 2);
    ctx.fillStyle = '#a5f3fc';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(lx, ly, 6, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(34,211,238,.16)';
    ctx.fill();
  }

  // 真实 CSI 里直流/保护子载波幅度恒为 0（本数据是 0-3、32、61-63），
  // 选中它们时波曲线是一条死线，所以下拉框里标「空载」并禁用，默认挑方差最大的活载波
  function refreshScPicker(force) {
    const sel = $('#scPick');
    if (!sel) return;
    const n = state.frames.length;
    if (n < 20) return;

    const dead = [];
    const live = [];
    for (let i = 0; i < SC; i++) {
      let lo = Infinity, hi = -Infinity;
      for (let k = 0; k < n; k++) {
        const v = state.frames[k][i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      (hi - lo > 1e-6 ? live : dead).push(i);
    }
    const sig = dead.join(',');
    if (!force && sig === state.scSig) return;
    state.scSig = sig;
    state.deadSc = dead;

    // 方差最大的活载波作为默认观测对象
    let best = live.length ? live[0] : 0;
    let bestVar = -1;
    for (let li = 0; li < live.length; li++) {
      const c = live[li];
      let m = 0;
      for (let k = 0; k < n; k++) m += state.frames[k][c];
      m /= n;
      let s = 0;
      for (let k = 0; k < n; k++) { const d = state.frames[k][c] - m; s += d * d; }
      if (s > bestVar) { bestVar = s; best = c; }
    }
    if (!state.scUser && dead.indexOf(state.subcarrier) >= 0) state.subcarrier = best;

    sel.innerHTML = Array.from({ length: SC }, (_, i) => {
      const isDead = dead.indexOf(i) >= 0;
      return '<option value="' + i + '"' + (i === state.subcarrier ? ' selected' : '') +
        (isDead ? ' disabled' : '') + '>' + i + (isDead ? ' (空载)' : '') + '</option>';
    }).join('');
    if (sel.value !== String(state.subcarrier)) sel.value = String(state.subcarrier);
  }

  function drawDecision() {
    const cv = $('#decisionCanvas');
    if (!cv) return;
    const box = fit(cv);
    if (!box) return;
    const { ctx, w, h } = box;

    const th = state.threshold;
    const yOf = (v) => h - v * h;
    const yTh = yOf(th);

    // 网格 + 刻度
    ctx.font = '12px ui-monospace, Consolas, monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let v = 0; v <= 1; v += 0.25) {
      const y = yOf(v);
      ctx.strokeStyle = 'rgba(126,156,210,.08)';
      ctx.beginPath();
      ctx.moveTo(0, y + .5);
      ctx.lineTo(w, y + .5);
      ctx.stroke();
      ctx.fillStyle = 'rgba(176,194,224,.92)';
      ctx.fillText(v.toFixed(2), w - 2, clamp(y, 6, h - 6));
    }

    const hist = state.history;
    if (!hist.length) return;
    const tEnd = nowMs();
    const SPAN = 30000;
    const xOf = (t) => w - ((tEnd - t) / SPAN) * w;

    // 有人区底色
    ctx.fillStyle = 'rgba(46,230,168,.055)';
    ctx.fillRect(0, 0, w, yTh);

    // 阈值线
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = 'rgba(232,238,251,.78)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, yTh + .5);
    ctx.lineTo(w, yTh + .5);
    ctx.stroke();
    ctx.restore();

    // 阈值标签
    ctx.textAlign = 'left';
    ctx.fillStyle = 'rgba(232,238,251,.86)';
    ctx.fillText('阈值 ' + th.toFixed(2), 4, clamp(yTh - 8, 8, h - 8));

    // 面积 + 折线
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < hist.length; i++) {
      const x = xOf(hist[i].t);
      if (x < -2) { started = false; continue; }
      const y = yOf(hist[i].s);
      if (!started) { ctx.moveTo(x, y); started = true; }
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = state.occupied ? '#2ee6a8' : '#6f9ad9';
    ctx.lineWidth = 1.6;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // 最新点
    const last = hist[hist.length - 1];
    const lx = xOf(last.t), ly = yOf(last.s);
    ctx.beginPath();
    ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fillStyle = state.occupied ? '#2ee6a8' : '#8bb1e6';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(lx, ly, 8, 0, Math.PI * 2);
    ctx.fillStyle = state.occupied ? 'rgba(46,230,168,.14)' : 'rgba(139,177,230,.14)';
    ctx.fill();
  }

  /* =========================================================
     六、实时主循环
     ========================================================= */
  let autoTimer = 0;
  const AUTO_SEQ = ['sitting', 'walking', 'vacant', 'fan', 'door', 'waving', 'sitting', 'vacant'];
  let autoIdx = 0;

  function setScene(key, opt) {
    if (!SCENES[key]) return;
    const prev = state.scene;
    state.scene = key;
    state.truth = !!SCENES[key].truth;
    autoTimer = 0;
    $$('#sceneGrid .scene').forEach(b => b.classList.toggle('active', b.dataset.scene === key));
    $('#heroTruth').textContent = '演示真值 · ' + (state.truth ? '有人' : '无人');
    if (prev !== key) {
      addEvent((SCENES[key].truth ? 'occ' : ''), '场景切换为 ' + SCENES[key].cn + '，真值 ' + (state.truth ? '有人' : '无人'));
    }
    if (!opt || !opt.silent) {
      // 用户手动点击时接管自动演示
      if (opt && opt.manual) {
        state.auto = false;
        $('#autoDemo').checked = false;
      }
    }
  }

  // 主词 / 判定徽标：之前只靠 CSS 换色，文字是写死的，会一直停在 VACANT
  function renderVerdict(next) {
    const en = $('#heroEn');
    const cn = $('#heroCn');
    const badge = $('#decisionBadge');
    if (en) en.textContent = next ? 'OCCUPIED' : 'VACANT';
    if (cn) cn.textContent = next ? '有人' : '无人';
    if (badge) {
      badge.textContent = next ? '有人' : '无人';
      badge.classList.toggle('on', !!next);
    }
  }

  function commitState(next, score) {
    state.occupied = next;
    state.lastSwitch = nowMs();
    state.switches++;
    document.body.dataset.occ = next ? '1' : '0';
    renderVerdict(next);

    if (state.truth === null) {
      // 实时流没有真值，只记录判定变化，不做误报/漏检统计
      addEvent(next ? 'occ' : '', '判定切换为 ' + (next ? '有人' : '无人') + '，分数 ' + score.toFixed(2));
    } else if (next !== state.truth) {
      if (next) state.fp++; else state.miss++;
      addEvent('bad', '判定与真值不一致：' + (next ? '误报（真值无人）' : '漏检（真值有人）') + '，分数 ' + score.toFixed(2));
    } else {
      addEvent(next ? 'occ' : '', '判定切换为 ' + (next ? '有人' : '无人') + '，分数 ' + score.toFixed(2));
    }
    $('#missCount').textContent = state.miss + ' / ' + state.fp;
  }

  function tick() {
    clockT += TICK_MS / 1000;

    // 1) 生成一帧（回放模式下帧由 replay.js 经 pushFrames 送入，这里不造假帧）
    if (state.source === 'demo') {
      const frame = genFrame(state.scene, clockT);
      state.frames.push(frame);
      if (state.frames.length > MAX_FRAMES) state.frames.shift();
    }

    // 2) 每 100 ms 更新一次分数与判定
    const t = nowMs();
    if (t - state.lastScoreAt >= 100) {
      state.lastScoreAt = t;

      let raw;
      if (state.source === 'replay' || state.source === 'live') {
        // 回放 / 实时：分数就是模型输出，不做平滑，抖动要如实暴露
        raw = state.externalScore;
      } else if (state.external && t - state.externalAt < 3000) {
        raw = state.externalScore;
      } else {
        state.external = false;
        raw = sceneScore(state.scene, clockT);
      }
      state.rawScore = raw;
      state.score = (state.source === 'replay' || state.source === 'live')
        ? raw
        : state.score + (raw - state.score) * state.smoothAlpha;

      // 最短驻留：候选状态需要持续满足
      const next = state.score >= state.threshold;
      if (next !== state.occupied) {
        if (next !== state.candidate) {
          state.candidate = next;
          state.candidateSince = t;
        } else if (t - state.candidateSince >= state.minDwell * 1000) {
          commitState(next, state.score);
        }
      } else {
        state.candidate = next;
        state.candidateSince = t;
      }

      // 历史（30 s）
      state.history.push({ t, s: state.score });
      while (state.history.length && state.history[0].t < t - 31000) state.history.shift();

      // 自动演示（仅模拟流模式）
      if (state.auto && state.source === 'demo') {
        autoTimer += 0.1;
        const dwell = Math.max(4, state.autoInterval) * (0.8 + 0.4 * Math.sin(autoIdx));
        if (autoTimer >= dwell) {
          autoIdx = (autoIdx + 1) % AUTO_SEQ.length;
          setScene(AUTO_SEQ[autoIdx], { silent: true });
        }
      }

      // 界面数值
      const f = windowFeatures(state.frames);
      $('#heroScore').textContent = state.score.toFixed(2);
      $('#meterFill').style.width = (state.score * 100).toFixed(1) + '%';
      $('#kpiAmp').textContent = f.amp.toFixed(1);
      $('#kpiAmpSub').textContent = '相对基线 ' + (((f.amp - BASE_AMP) / BASE_AMP) * 100).toFixed(1) + '%';
      $('#kpiMotion').textContent = f.diff.toFixed(2);
      $('#kpiMotionSub').textContent = '峰值跳变 ' + f.jump.toFixed(2);
      $('#kpiWin').textContent = state.frames.length;

      // 包率：按数据集的标称采样率模拟，叠加轻微抖动
      const nominal = (META && META.dataset && META.dataset.sampleRate) || 100;
      const rate = Math.round(nominal * (0.96 + Math.random() * 0.08));
      $('#kpiRate').textContent = rate;
      $('#rateBar').style.width = Math.min(100, (rate / (nominal * 1.08)) * 100).toFixed(0) + '%';

      const occP = state.score;
      $('#probOcc').style.width = (occP * 100).toFixed(1) + '%';
      $('#probVac').style.width = ((1 - occP) * 100).toFixed(1) + '%';
      $('#probOccNum').textContent = Math.round(occP * 100) + '%';
      $('#probVacNum').textContent = Math.round((1 - occP) * 100) + '%';

      $('#dwell').textContent = ((t - state.lastSwitch) / 1000).toFixed(1) + 's';
      const runS = Math.floor((t - state.runStart) / 1000);
      $('#sessionDur').textContent = pad2(Math.floor(runS / 60)) + ':' + pad2(runS % 60);
      $('#switches').textContent = state.switches;

      drawHeat();
      drawLine();
      drawDecision();
    }

    // 3) 每秒一格时间线
    const sec = Math.floor(clockT);
    if (sec !== state.lastSecond) {
      state.lastSecond = sec;
      state.timeline.push(state.occupied ? 1 : 0);
      if (state.timeline.length > 60) state.timeline.shift();
      renderTimeline();
      tickClock();
    }
  }

  function renderTimeline() {
    const host = $('#timeline');
    if (!host) return;
    const cells = [];
    const missing = 60 - state.timeline.length;
    for (let i = 0; i < missing; i++) cells.push('<i></i>');
    state.timeline.forEach(v => cells.push(v ? '<i class="occ"></i>' : '<i class="vac"></i>'));
    host.innerHTML = cells.join('');
  }

  function tickClock() {
    const d = new Date();
    $('#clock').textContent = pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  /* =========================================================
     七、事件日志
     ========================================================= */
  function addEvent(kind, text) {
    const t = new Date();
    const stamp = pad2(t.getHours()) + ':' + pad2(t.getMinutes()) + ':' + pad2(t.getSeconds());
    const key = text.slice(0, 18);
    if (state.lastEventKey === key && nowMs() - state.lastEventAt < 1200) return;
    state.lastEventKey = key;
    state.lastEventAt = nowMs();
    state.events.unshift({ stamp, kind, text });
    if (state.events.length > 30) state.events.pop();
    renderEvents();
  }

  function renderEvents() {
    const host = $('#eventList');
    if (!host) return;
    if (!state.events.length) {
      host.innerHTML = '<li class="empty">等待状态变化…</li>';
      return;
    }
    host.innerHTML = state.events.slice(0, 8).map(e =>
      '<li><span class="bullet ' + e.kind + '"></span><time>' + e.stamp + '</time><span class="txt">' + e.text + '</span></li>'
    ).join('');
  }

  /* =========================================================
     八、评估页：混淆矩阵 / 阈值曲线 / 分布 / 分文件
     ========================================================= */
  function renderEval(th) {
    const m = metricsAt(th);

    // 混淆矩阵
    $('#cmTN').querySelector('b').textContent = m.tn;
    $('#cmTP').querySelector('b').textContent = m.tp;
    $('#cmFP').querySelector('b').textContent = m.fp;
    $('#cmFN').querySelector('b').textContent = m.fn;

    // 当前阈值下高亮最大误差格
    const cells = { TN: $('#cmTN'), TP: $('#cmTP'), FP: $('#cmFP'), FN: $('#cmFN') };
    Object.values(cells).forEach(c => c.classList.remove('hl'));
    const worst = [['FP', m.fp], ['FN', m.fn], ['TN', m.tn], ['TP', m.tp]].sort((a, b) => b[1] - a[1]);
    if (worst[0][1] > 0 && (worst[0][0] === 'FP' || worst[0][0] === 'FN')) cells[worst[0][0]].classList.add('hl');

    $('#cmDerived').innerHTML = [
      ['精确率 Precision', pct(m.prec)],
      ['召回率 Recall', pct(m.sens)],
      ['特异度 Specificity', pct(m.spec)],
      ['F1', m.f1.toFixed(3)]
    ].map(([k, v]) => '<div><span>' + k + '</span><b>' + v + '</b></div>').join('');

    // 阈值读数
    $('#evalThrVal').textContent = th.toFixed(2);
    $('#evalThr').value = Math.round(th * 100);
    $('#evalMetrics').innerHTML = [
      ['准确率', pct(m.acc)],
      ['平衡准确率', pct(m.bal)],
      ['真阳 TP', m.tp],
      ['假阳 FP', m.fp],
      ['假阴 FN', m.fn]
    ].map(([k, v]) => '<div><span>' + k + '</span><b>' + v + '</b></div>').join('');

    // 混淆矩阵说明随阈值变化
    const near = Math.abs(th - 0.5) < 0.005;
    $('#cmSub').textContent = '阈值 ' + th.toFixed(2) + (near ? ' · 报告口径' : ' · 已偏离报告');
    $('#cmNote').textContent = (m.fp || m.fn)
      ? '主要误差来自“无人 → 判有人”（' + m.fp + ' 例，占测试窗口 ' + pct(m.fp / m.n) +
        '）与“有人 → 判无人”（' + m.fn + ' 例）。'
      : '当前阈值下没有误判窗口。';

    // 提示
    const baseAcc = META.accuracy == null ? m.acc : META.accuracy;
    const delta = m.acc - baseAcc;
    let note;
    if (Math.abs(th - 0.5) < 0.005) {
      note = META.accuracy == null
        ? '当前阈值 0.50：准确率 ' + pct(m.acc) + '（数据未提供报告指标，此值为窗口重算）。'
        : '阈值 0.50 与报告一致：准确率 ' + pct(META.accuracy) + '、平衡准确率 ' + pct(META.balanced) + '。';
    } else {
      const sign = delta >= 0 ? '+' : '';
      note = '阈值 ' + th.toFixed(2) + '：准确率 ' + pct(m.acc) + '（' + sign + (delta * 100).toFixed(1) + ' 个百分点）。' +
        '这是在同一测试集上移动阈值的结果，属于乐观估计，不能当作模型提升。';
    }
    $('#thrNote').textContent = note;

    drawThresholdCurve(th);
    drawDist(th);
    renderPerFile();
  }

  function drawThresholdCurve(curTh) {
    const cv = $('#thresholdCanvas');
    if (!cv) return;
    const box = fit(cv);
    if (!box) return;
    const { ctx, w, h } = box;

    const padL = 42, padR = 12, padT = 12, padB = 24;
    const iw = w - padL - padR;
    const ih = h - padT - padB;
    const xOf = (th) => padL + ((th - 0.05) / 0.9) * iw;
    const yOf = (v) => padT + (1 - (v - 0.4) / 0.5) * ih;

    ctx.font = '12px ui-monospace, Consolas, monospace';
    ctx.textBaseline = 'middle';

    // 网格
    for (let v = 0.4; v <= 0.9001; v += 0.1) {
      const y = yOf(v);
      ctx.strokeStyle = 'rgba(126,156,210,.08)';
      ctx.beginPath();
      ctx.moveTo(padL, y + .5);
      ctx.lineTo(w - padR, y + .5);
      ctx.stroke();
      ctx.fillStyle = 'rgba(176,194,224,.86)';
      ctx.textAlign = 'right';
      ctx.fillText(Math.round(v * 100) + '%', padL - 6, y);
    }
    ctx.textAlign = 'center';
    [0.1, 0.3, 0.5, 0.7, 0.9].forEach(v => {
      const x = xOf(v);
      ctx.strokeStyle = 'rgba(126,156,210,.06)';
      ctx.beginPath();
      ctx.moveTo(x + .5, padT);
      ctx.lineTo(x + .5, h - padB);
      ctx.stroke();
      ctx.fillStyle = 'rgba(176,194,224,.86)';
      ctx.fillText(v.toFixed(1), x, h - padB + 11);
    });

    const line = (key, color, width) => {
      ctx.beginPath();
      CURVE.forEach((p, i) => {
        const x = xOf(p.th), y = yOf(p[key]);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineJoin = 'round';
      ctx.stroke();
    };
    line('acc', 'rgba(46,230,168,.9)', 1.7);
    line('bal', 'rgba(34,211,238,.75)', 1.2);

    // 当前阈值
    const x = xOf(curTh);
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = 'rgba(232,238,251,.72)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + .5, padT);
    ctx.lineTo(x + .5, h - padB);
    ctx.stroke();
    ctx.restore();

    const m = metricsAt(curTh);
    [[m.acc, '#2ee6a8'], [m.bal, '#22d3ee']].forEach(([v, c]) => {
      ctx.beginPath();
      ctx.arc(x, yOf(v), 3, 0, Math.PI * 2);
      ctx.fillStyle = c;
      ctx.fill();
    });

    // 图例
    ctx.textAlign = 'left';
    ctx.fillStyle = 'rgba(46,230,168,.85)';
    ctx.fillRect(w - padR - 96, padT + 2, 10, 2);
    ctx.fillStyle = 'rgba(176,194,224,.95)';
    ctx.fillText('准确率', w - padR - 80, padT + 3);
    ctx.fillStyle = 'rgba(34,211,238,.8)';
    ctx.fillRect(w - padR - 42, padT + 2, 10, 2);
    ctx.fillStyle = 'rgba(176,194,224,.95)';
    ctx.fillText('平衡', w - padR - 26, padT + 3);
  }

  // 分布图：行 = 文件，x = 分数
  let distPoints = [];
  function drawDist(curTh) {
    const cv = $('#distCanvas');
    if (!cv) return;
    const box = fit(cv);
    if (!box) return;
    const { ctx, w, h } = box;

    // 行来自 perFile；若报告未提供，则回退到预测文件清单
    const files = Object.keys(META.perFile).length
      ? Object.keys(META.perFile)
      : Array.from(new Set(WINDOWS.map(w => w.f)));
    if (!files.length) return;
    const padL = 132, padR = 16, padT = 14, padB = 26;
    const iw = w - padL - padR;
    const ih = h - padT - padB;
    const rowH = ih / files.length;
    const xOf = (s) => padL + s * iw;

    // 网格
    ctx.font = '12px ui-monospace, Consolas, monospace';
    ctx.textBaseline = 'middle';
    for (let v = 0; v <= 1.0001; v += 0.2) {
      const x = xOf(v);
      ctx.strokeStyle = 'rgba(126,156,210,.08)';
      ctx.beginPath();
      ctx.moveTo(x + .5, padT);
      ctx.lineTo(x + .5, h - padB);
      ctx.stroke();
      ctx.fillStyle = 'rgba(176,194,224,.82)';
      ctx.textAlign = 'center';
      ctx.fillText(v.toFixed(1), x, h - padB + 10);
    }

    // 行标签
    ctx.textAlign = 'right';
    files.forEach((f, i) => {
      const cy = padT + rowH * i + rowH / 2;
      ctx.fillStyle = 'rgba(176,194,224,.95)';
      const name = f.replace('.jsonl', '');
      ctx.fillText(name.length > 13 ? name.slice(0, 12) + '…' : name, padL - 10, cy);
    });

    // 阈值线
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = 'rgba(232,238,251,.72)';
    ctx.beginPath();
    const tx = xOf(curTh);
    ctx.moveTo(tx + .5, padT - 4);
    ctx.lineTo(tx + .5, h - padB);
    ctx.stroke();
    ctx.restore();

    distPoints = [];
    const jitter = (i, k) => (Math.sin(i * 12.9898 + k * 78.233) * 0.5) * (rowH * 0.34);

    WINDOWS.forEach((win, idx) => {
      const ri = files.indexOf(win.f);
      if (ri < 0) return;
      const cy = padT + rowH * ri + rowH / 2;
      const x = xOf(win.sc);
      const y = cy + jitter(ri, idx);
      distPoints.push({ x, y, win, r: 4.2 });

      ctx.beginPath();
      ctx.arc(x, y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = win.y === 1 ? 'rgba(46,230,168,.85)' : 'rgba(139,177,230,.78)';
      ctx.fill();
      ctx.strokeStyle = win.y === 1 ? 'rgba(46,230,168,.28)' : 'rgba(139,177,230,.26)';
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    // 阈值上方误报区提示
    ctx.fillStyle = 'rgba(251,113,133,.8)';
    ctx.textAlign = 'right';
    ctx.fillText('阈值右侧判为有人', w - padR, padT - 4);
  }

  // 分布图 hover
  let tooltip = null;
  function initDistHover() {
    const cv = $('#distCanvas');
    if (!cv) return;
    tooltip = document.createElement('div');
    tooltip.className = 'dist-tip';
    tooltip.style.cssText = 'position:absolute;pointer-events:none;opacity:0;transition:opacity .12s;' +
      'background:rgba(10,15,27,.96);border:1px solid rgba(126,156,210,.3);border-radius:7px;' +
      'padding:6px 9px;font-size:10px;line-height:1.55;color:#e8eefb;white-space:nowrap;z-index:5;' +
      'box-shadow:0 10px 24px -14px #000;font-family:var(--mono)';
    cv.parentElement.style.position = 'relative';
    cv.parentElement.appendChild(tooltip);

    cv.addEventListener('mousemove', (ev) => {
      const r = cv.getBoundingClientRect();
      const mx = ev.clientX - r.left, my = ev.clientY - r.top;
      let best = null, bestD = 1e9;
      for (const p of distPoints) {
        const d = (p.x - mx) ** 2 + (p.y - my) ** 2;
        if (d < bestD) { bestD = d; best = p; }
      }
      if (!best || bestD > 90) { tooltip.style.opacity = 0; return; }
      const w = best.win;
      tooltip.innerHTML = w.f.replace('.jsonl', '') + '<br>' +
        '窗口 ' + w.s.toFixed(0) + '–' + w.e.toFixed(0) + ' s<br>' +
        '真值 ' + (w.y ? '有人' : '无人') + ' · 分数 ' + w.sc.toFixed(3);
      tooltip.style.left = Math.min(r.width - 150, Math.max(4, best.x + 10)) + 'px';
      tooltip.style.top = Math.max(2, best.y - 54) + 'px';
      tooltip.style.opacity = 1;
    });
    cv.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
  }

  function renderPerFile() {
    const host = $('#perFileBars');
    if (!host) return;
    const files = Object.keys(META.perFile);
    if (!files.length) {
      host.innerHTML = '<p class="note">该数据集未提供分文件准确率。</p>';
      return;
    }
    host.innerHTML = files.map(f => {
      const row = META.perFile[f];
      const acc = row.accuracy;
      const color = acc >= 0.9 ? 'var(--occ)' : acc >= 0.7 ? 'var(--warn)' : 'var(--bad)';
      return '<div class="pf-row">' +
        '<span class="pf-name" title="' + f + '">' + f.replace('.jsonl', '') + '</span>' +
        '<div class="pf-track"><i style="width:' + (acc * 100).toFixed(1) + '%;background:' + color + '"></i></div>' +
        '<span class="pf-val">' + pct(acc, 0) + '</span>' +
        '</div>';
    }).join('');
  }

  /* =========================================================
     九、数据页
     ========================================================= */
  function renderData() {
    const files = DATA.audit || [];
    const excluded = files.filter(a => a.split === 'exclude').length;
    const nTrain = files.filter(a => a.split === 'train').length;
    const nTest = files.filter(a => a.split === 'test').length;
    const ds = META.dataset;

    const summary = [
      ['录制文件', files.length, '单批次 · ' + ds.device],
      ['纳入标签', files.length - excluded, excluded + ' 个文件因跨状态排除'],
      ['训练窗口', META.trainWindows, nTrain + ' 个文件'],
      ['测试窗口', META.testWindows, nTest + ' 个文件'],
      ['子载波', SC, ds.sampleRate + ' Hz'],
      ['类别', 2, '有人 / 无人']
    ];
    $('#dataSummary').innerHTML = summary.map(([k, v, s]) =>
      '<div class="stat"><span>' + k + '</span><b>' + v + '</b><small>' + s + '</small></div>'
    ).join('');

    // 备注优先取数据文件里的 notes，其次按文件名关键字推断，最后留空
    const HINTS = [
      ['空场', '空场 · 无人'],
      ['风扇', '风扇干扰 · 应判无人'],
      ['门口', '门外经过 · 应判无人'],
      ['走动', '区域内有人员走动'],
      ['挥手', '区域内有人挥手'],
      ['玩电脑', '区域内有人打字'],
      ['起身', '跨越状态 · 不参与训练']
    ];
    const pick = (name) => {
      const note = (META.notes && META.notes[name]) || '';
      if (note) return note;
      for (const [k, v] of HINTS) if (name.indexOf(k) >= 0) return v;
      return '—';
    };

    const rows = DATA.audit.slice().sort((a, b) => {
      const rank = (x) => x.split === 'test' ? 0 : x.split === 'train' ? 1 : 2;
      return rank(a) - rank(b);
    });

    $('#dataTable').innerHTML = rows.map(a => {
      const labelTag = a.label === '1'
        ? '<span class="tag occ">有人</span>'
        : a.label === '0'
          ? '<span class="tag vac">无人</span>'
          : '<span class="tag exclude">排除</span>';
      const splitTag = a.split === 'exclude' ? '<span class="muted">—</span>' : '<span class="tag split">' + a.split + '</span>';
      const pf = META.perFile[a.f];
      const accCell = a.split === 'test' && pf
        ? '<span class="mono" style="color:' + (pf.accuracy >= 0.9 ? 'var(--occ)' : pf.accuracy >= 0.7 ? 'var(--warn)' : 'var(--bad)') + '">' + pct(pf.accuracy, 1) + '</span>'
        : a.split === 'train' ? '<span class="mono muted">训练</span>' : '<span class="mono muted">—</span>';
      return '<tr>' +
        '<td class="name" title="' + a.f + '">' + a.f.replace('.jsonl', '') + '</td>' +
        '<td>' + labelTag + '</td>' +
        '<td>' + splitTag + '</td>' +
        '<td class="mono">' + a.frames + '</td>' +
        '<td class="mono">' + a.dur.toFixed(1) + 's</td>' +
        '<td class="mono">' + a.acc + '</td>' +
        '<td>' + accCell + '</td>' +
        '<td class="muted">' + pick(a.f) + '</td>' +
        '</tr>';
    }).join('');

    // 局限说明来自数据文件（report.json 的 limitations），不再硬编码
    $('#limitList').innerHTML = META.limits.map(t => {
      const hit = LIMIT_ZH.find(([en]) => t.indexOf(en) === 0);
      return '<li>' + (hit ? hit[1] : t) + '</li>';
    }).join('');
  }

  /* =========================================================
     十、视图切换
     ========================================================= */
  function switchView(route) {
    $$('.route-btn').forEach(b => b.classList.toggle('active', b.dataset.route === route));
    $$('.view').forEach(v => v.classList.toggle('active', v.dataset.view === route));
    if (route === 'eval') requestAnimationFrame(() => renderEval(state.evalThreshold));
    if (route === 'data') renderData();
    try {
      const url = new URL(location.href);
      url.hash = route;
      history.replaceState(null, '', url);
    } catch (e) { /* file:// 下可能被拒绝，忽略 */ }
  }

  /* =========================================================
     十一、交互绑定
     ========================================================= */
  function bind() {
    $$('.route-btn').forEach(b => b.addEventListener('click', () => switchView(b.dataset.route)));

    // 运行阈值（侧栏）
    $('#sideThr').addEventListener('input', (e) => {
      const th = Number(e.target.value) / 100;
      state.threshold = th;
      $('#sideThrVal').textContent = th.toFixed(2);
      $('#meterMark').style.left = (th * 100) + '%';
      $('#meterMark').querySelector('em').textContent = th.toFixed(2);
      const note = th < 0.44
        ? '阈值偏低：更多窗口会判为有人，误报上升、漏检下降。'
        : th > 0.56
          ? '阈值偏高：误报下降，但有人静坐时更容易漏检。'
          : '接近报告阈值 0.50，与评估口径一致。';
      $('#sideThrNote').textContent = note;
      if ($('#cfgThr')) $('#cfgThr').value = th.toFixed(2);
      drawDecision();
    });

    // 场景
    $$('#sceneGrid .scene').forEach(btn => {
      btn.addEventListener('click', () => {
        setScene(btn.dataset.scene, { manual: true });
        toast('已切换到：' + SCENES[btn.dataset.scene].cn);
      });
    });
    $('#autoDemo').addEventListener('change', (e) => {
      state.auto = e.target.checked;
      autoTimer = 0;
      toast(state.auto ? '自动演示已开启' : '自动演示已暂停，由你手动控制');
    });

    // 子载波
    const sel = $('#scPick');
    sel.addEventListener('change', (e) => {
      state.subcarrier = Number(e.target.value);
      state.scUser = true;
      drawLine();
    });
    refreshScPicker(true);

    // 清空日志
    $('#btnClearLog').addEventListener('click', () => {
      state.events = [];
      renderEvents();
    });

    // 评估阈值
    $('#evalThr').addEventListener('input', (e) => {
      state.evalThreshold = Number(e.target.value) / 100;
      renderEval(state.evalThreshold);
    });
    $('#btnThrReset').addEventListener('click', () => {
      state.evalThreshold = 0.5;
      renderEval(0.5);
    });

    // 设置页
    $('#btnApplyCfg').addEventListener('click', () => {
      const th = clamp(Number($('#cfgThr').value) || 0.5, 0.05, 0.95);
      const dwell = clamp(Number($('#cfgDwell').value) || 1, 0, 10);
      const alpha = clamp(Number($('#cfgSmooth').value) || 0.35, 0.05, 1);
      const auto = clamp(Number($('#cfgAuto').value) || 12, 4, 60);

      state.threshold = th;
      state.minDwell = dwell;
      state.smoothAlpha = alpha;
      state.autoInterval = auto;
      autoTimer = 0;

      $('#sideThr').value = Math.round(th * 100);
      $('#sideThrVal').textContent = th.toFixed(2);
      $('#meterMark').style.left = (th * 100) + '%';
      $('#meterMark').querySelector('em').textContent = th.toFixed(2);
      toast('参数已应用：阈值 ' + th.toFixed(2) + ' · 驻留 ' + dwell.toFixed(1) + 's');
    });

    $('#btnResetCfg').addEventListener('click', () => {
      $('#cfgThr').value = DEFAULT.threshold.toFixed(2);
      $('#cfgDwell').value = DEFAULT.minDwell.toFixed(1);
      $('#cfgSmooth').value = DEFAULT.smoothAlpha;
      $('#cfgAuto').value = DEFAULT.autoInterval;
      state.threshold = DEFAULT.threshold;
      state.minDwell = DEFAULT.minDwell;
      state.smoothAlpha = DEFAULT.smoothAlpha;
      state.autoInterval = DEFAULT.autoInterval;
      $('#sideThr').value = 50;
      $('#sideThrVal').textContent = '0.50';
      $('#meterMark').style.left = '50%';
      $('#meterMark').querySelector('em').textContent = '0.50';
      toast('已恢复默认参数');
    });

    window.addEventListener('resize', () => {
      drawHeat();
      drawLine();
      drawDecision();
      if ($('.view[data-view="eval"]').classList.contains('active')) {
        drawThresholdCurve(state.evalThreshold);
        drawDist(state.evalThreshold);
      }
    });
  }

  function toast(msg) {
    const host = $('#toastHost');
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity .25s, transform .25s';
      el.style.opacity = 0;
      el.style.transform = 'translateY(6px)';
      setTimeout(() => el.remove(), 260);
    }, 1900);
  }

  /* =========================================================
     十二、对外接入 API
     ========================================================= */
  window.CSIOcc = {
    pushPrediction(score) {
      state.externalScore = clamp(Number(score), 0, 1);
      state.external = true;
      state.externalAt = nowMs();
    },
    pushFrame(amp) {
      if (!amp || amp.length !== SC) return false;
      state.frames.push(Float32Array.from(amp));
      if (state.frames.length > MAX_FRAMES) state.frames.shift();
      drawHeat();
      drawLine();
      return true;
    },
    // 批量送帧：回放按 100 Hz 喂入，每批只重绘一次，避免 100 次/秒的 canvas 抖动
    pushFrames(list) {
      if (!list || !list.length) return 0;
      let n = 0;
      for (let i = 0; i < list.length; i++) {
        const amp = list[i];
        if (!amp || amp.length !== SC) continue;
        state.frames.push(amp instanceof Float32Array ? amp : Float32Array.from(amp));
        n++;
      }
      if (!n) return 0;
      while (state.frames.length > MAX_FRAMES) state.frames.shift();
      refreshScPicker();
      drawHeat();
      drawLine();
      return n;
    },
    setSource(mode) {
      state.source = (mode === 'replay' || mode === 'live') ? mode : 'demo';
      state.frames.length = 0;
      state.external = false;
      state.history.length = 0;
      state.timeline.length = 0;
      state.lastSecond = -1;
      if (state.source !== 'demo') {
        state.auto = false;
        const chk = $('#autoDemo');
        if (chk) chk.checked = false;
      }
      const el = $('#srcState');
      if (el) el.textContent = state.source === 'replay' ? '真实回放'
        : (state.source === 'live' ? '实时连接' : '模拟流');
      document.body.dataset.source = state.source;
      // 换源时清掉旧判定，避免演示态的结果残留到回放/实时里
      state.score = 0;
      state.rawScore = 0;
      state.externalScore = 0;
      state.candidate = false;
      state.occupied = false;
      state.lastSwitch = nowMs();
      document.body.dataset.occ = '0';
      renderVerdict(false);
      if (state.source === 'live') {
        // 实时流没有真值：清掉真值显示，别把演示真值带进来
        state.truth = null;
        const ht = $('#heroTruth');
        if (ht) ht.textContent = '实时流 · 无真值';
      }
      addEvent('', '数据源切换为' + (state.source === 'replay' ? '真实回放（浏览器内推理）'
        : (state.source === 'live' ? '实时监控（浏览器内推理）' : '模拟流')));
      return state.source;
    },
    setTruth(flag) {
      state.truth = flag === null ? null : !!flag;
      const el = $('#heroTruth');
      if (!el) return;
      if (state.truth === null) {
        el.textContent = '实时流 · 无真值';
        return;
      }
      el.textContent = (state.source === 'replay' ? '回放真值 · ' : '演示真值 · ')
        + (state.truth ? '有人' : '无人');
    },
    setThreshold(th) {
      const v = clamp(Number(th), 0.05, 0.95);
      state.threshold = v;
      const el = $('#sideThr');
      if (el) { el.value = Math.round(v * 100); el.dispatchEvent(new Event('input')); }
    },
    getState() {
      return {
        occupied: state.occupied,
        score: Number(state.score.toFixed(4)),
        threshold: state.threshold,
        scene: state.scene,
        dataset: META.dataset.id,
        model: META.model.id,
        source: state.source === 'replay' ? 'replay'
          : (state.source === 'live' ? 'live' : (state.external ? 'external' : 'demo')),
        framesInBuffer: state.frames.length,
        modelLoaded: !!(window.CSIInfer && window.CSIInfer.ready),
        verdictText: { en: $('#heroEn') && $('#heroEn').textContent, cn: $('#heroCn') && $('#heroCn').textContent },
        lineRange: lineDebug()
      };
    }
  };

  // 时波观测窗口的取值区间，用于排查"曲线贴边"这类缩放问题
  function lineDebug() {
    const n = state.frames.length;
    if (n < 2) return null;
    const sc = Math.min(state.subcarrier, SC - 1);
    let lo = Infinity, hi = -Infinity, bad = 0;
    for (let k = 0; k < n; k++) {
      const v = state.frames[k][sc];
      if (!Number.isFinite(v)) { bad++; continue; }
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    return {
      n, sc, len: state.frames[0].length, bad,
      lo: Number(lo.toFixed(3)), hi: Number(hi.toFixed(3)),
      first: Number(state.frames[0][sc].toFixed(3)),
      last: Number(state.frames[n - 1][sc].toFixed(3))
    };
  }

  /* =========================================================
     十三、数据装载与元信息渲染
     ========================================================= */
  function loadData() {
    const src = new URLSearchParams(location.search).get('data');
    if (!src) {
      if (window.CSI_DATA) return Promise.resolve(window.CSI_DATA);
      return Promise.reject(new Error('未找到 assets/data.js，也未指定 ?data= 参数'));
    }
    return fetch(src, { cache: 'no-store' }).then(res => {
      if (!res.ok) throw new Error('HTTP ' + res.status + '：' + src);
      return res.json();
    });
  }

  function normalizeMeta() {
    DATA = DATA || {};
    DATA.windows = DATA.windows || [];
    DATA.audit = DATA.audit || [];
    META = DATA.meta || {};

    META.dataset = Object.assign({
      id: 'default', name: '未命名数据集', task: 'effective_zone_occupancy',
      device: '—', room: '—', subcarriers: 64, sampleRate: 100,
      files: DATA.audit.length, frames: 0, durationSec: 0
    }, META.dataset || {});

    // 房间号缺失时从数据集名里推（如「6B514 批次 1」）
    if (!META.dataset.room || META.dataset.room === '—') {
      const m = /\b([0-9][A-Za-z0-9]{3,5})\b/.exec(String(META.dataset.name || ''));
      if (m) META.dataset.room = m[1];
    }

    META.model = Object.assign({
      id: 'unknown', name: '未指定模型', algo: '',
      trees: null, maxDepth: null, minLeaf: null,
      windowSec: 2.0, trimSec: 1.0, runtime: '—'
    }, META.model || {});

    META.perFile = META.perFile || {};
    META.limits = (META.limits && META.limits.length) ? META.limits : ['该数据集未提供局限说明。'];
    if (META.trainWindows == null) META.trainWindows = 0;
    if (META.testWindows == null) META.testWindows = DATA.windows.length;

    SC = Number(META.dataset.subcarriers) || 64;
  }

  function perFileNoteText() {
    const ds = META.dataset;
    const same = ds.device && ds.device !== '—'
      ? '同一设备（' + ds.device + '）与采集条件'
      : '同一采集条件';
    return '各测试文件在' + same + '下录制；该批次已被查看过，属于开发期留出集，不是盲测。';
  }

  function describeErrors() {
    if (!WINDOWS.length) return '该数据集没有逐窗口预测，无法绘制分数分布。';
    const fpBy = {};
    WINDOWS.forEach(w => {
      if (w.y === 0 && w.sc >= 0.5) fpBy[w.f] = (fpBy[w.f] || 0) + 1;
    });
    const top = Object.keys(fpBy).map(k => [k, fpBy[k]]).sort((a, b) => b[1] - a[1])[0];
    if (!top) return '阈值 0.50 下没有误报窗口，分布图只反映两类分数的分离度。';
    return '阈值 0.50 下误报集中在「' + top[0].replace(/\.jsonl$/i, '') +
      '」（' + top[1] + ' 个窗口），是当前主要假阳来源。';
  }

  function renderDatasetPicker() {
    const list = window.CSI_DATASETS || [];
    if (list.length < 2) return;
    const wrap = $('#dsPickWrap'), sel = $('#dsPick');
    if (!wrap || !sel) return;
    const cur = new URLSearchParams(location.search).get('data') || '';
    sel.innerHTML = list.map(d =>
      '<option value="' + (d.src || '') + '">' + (d.label || d.src) + '</option>').join('');
    sel.value = list.some(d => (d.src || '') === cur) ? cur : (list[0].src || '');
    wrap.hidden = false;
    sel.addEventListener('change', () => {
      const v = sel.value;
      location.search = v ? '?data=' + encodeURIComponent(v) : '';
    });
  }

  function renderChrome() {
    const ds = META.dataset, md = META.model;
    const m05 = metricsAt(0.5);

    // 侧栏采集状态
    $('#kvDevice').textContent = ds.device || '—';
    $('#kvRoom').textContent = ds.room || '—';
    $('#kvSc').textContent = SC;
    $('#kvRate').textContent = (ds.sampleRate || 100) + ' Hz';
    $('#heatSub').textContent = SC + ' 子载波 × 最近 5 秒';
    $('#kpiWinSub').textContent = Number(md.windowSec).toFixed(1) + ' s · 步长 ' +
      Number(md.windowSec).toFixed(1) + ' s';

    // 顶栏
    $('#modelChip').innerHTML = '<i></i>' + md.name + ' · 二分类';

    // 评估页概览
    const acc = META.accuracy == null ? m05.acc : META.accuracy;
    const bal = META.balanced == null ? m05.bal : META.balanced;
    $('#statAcc').textContent = (acc * 100).toFixed(1);
    $('#statAccSub').textContent = 'Accuracy · ' + (m05.tp + m05.tn) + ' / ' + m05.n + ' 窗口';
    $('#statBal').textContent = (bal * 100).toFixed(1);
    $('#statBase').textContent = META.baseline == null ? '—' : (META.baseline * 100).toFixed(1);
    $('#statTrain').textContent = META.trainWindows;
    $('#statTest').textContent = '+' + META.testWindows;
    $('#thrPanelSub').textContent = '拖动阈值，用 ' + WINDOWS.length + ' 个真实测试窗口重算';
    const testFileCount = Object.keys(META.perFile).length ||
      new Set(WINDOWS.map(w => w.f)).size;
    $('#perFileSub').textContent = '测试集 ' + testFileCount + ' 个文件';
    $('#perFileNote').textContent = perFileNoteText();

    // 设置页只读信息
    const hp = [];
    if (md.trees) hp.push(md.trees + ' 棵树');
    if (md.maxDepth) hp.push('depth ' + md.maxDepth);
    if (md.minLeaf) hp.push('leaf ' + md.minLeaf);
    const kv = [
      ['任务', ds.task || '—'],
      ['数据集', ds.name],
      ['模型', md.name + (md.algo ? ' · ' + md.algo : '')],
      ['超参数', hp.join(' · ') || '—'],
      ['特征', '4 × ' + SC + ' = ' + (4 * SC) + ' 维'],
      ['窗口 / 修剪', Number(md.windowSec).toFixed(1) + ' s / ' + Number(md.trimSec).toFixed(1) + ' s'],
      ['设备 / 房间', (ds.device || '—') + ' / ' + (ds.room || '—')],
      ['运行环境', md.runtime || '—']
    ];
    $('#modelKv').innerHTML = kv.map(([k, v]) =>
      '<div class="kv"><span>' + k + '</span><b>' + v + '</b></div>').join('');

    // 页脚
    $('#footDataset').textContent = ds.name + ' · ' + DATA.audit.length + ' 个文件 · ' +
      DATA.windows.length + ' 个测试窗口';
    $('#footModel').textContent = md.name + (md.runtime && md.runtime !== '—' ? ' · ' + md.runtime : '');
    const gen = META.generated || {};
    $('#footGenerated').textContent = gen.at ? '数据生成于 ' + gen.at : '数据已加载';

    $('#distNote').textContent = describeErrors();
    renderDatasetPicker();

    document.title = 'CSI 占据检测 · ' + ds.name + ' · 二分类实验台';
  }

  function showFatal(err) {
    console.error(err);
    const msg = '数据加载失败：' + (err && err.message ? err.message : String(err));
    const host = $('#toastHost');
    if (host) {
      const el = document.createElement('div');
      el.className = 'toast';
      el.style.opacity = 1;
      el.textContent = msg;
      host.appendChild(el);
    }
    const chip = $('#modelChip');
    if (chip) chip.innerHTML = '<i></i>数据加载失败';
    ['footDataset', 'footModel', 'footGenerated'].forEach(id => {
      const el = $('#' + id);
      if (el) el.textContent = '—';
    });
  }

  /* =========================================================
     十四、启动
     ========================================================= */
  async function boot() {
    try {
      DATA = await loadData();
    } catch (err) {
      showFatal(err);
      return;
    }
    normalizeMeta();
    WINDOWS = DATA.windows;
    buildCurve();
    buildProfile();
    state.subcarrier = Math.min(32, SC - 1);

    bind();
    renderChrome();
    renderEvents();
    renderTimeline();
    tickClock();
    setScene('vacant', { silent: true });
    state.lastSwitch = nowMs();
    document.body.dataset.occ = '0';
    renderVerdict(false);

    // 预热几帧，避免首屏空白
    for (let i = 0; i < 40; i++) {
      clockT += TICK_MS / 1000;
      state.frames.push(genFrame(state.scene, clockT));
    }
    state.score = 0.14;
    refreshScPicker(true);

    initDistHover();
    renderEval(0.5);
    renderData();

    setInterval(tick, TICK_MS);
    addEvent('', '实验台启动，默认模拟流（可在左侧「数据源」切到真实回放）');

    // 支持 #live / #eval / #data / #setup 直达
    const route = (location.hash || '').replace(/^#/, '');
    if (route && $('.view[data-view="' + route + '"]')) switchView(route);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
