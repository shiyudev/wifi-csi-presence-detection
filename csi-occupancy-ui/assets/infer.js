/*!
 * infer.js — 浏览器内随机森林推理（无需后端、无需 WASM）
 *
 * 由 _work/export_model.py 导出的 assets/model.js 提供 window.CSI_MODEL，
 * 本文件负责「振幅窗口 → 256 维特征 → 分数」，与 Python 侧逐位对齐。
 *
 * 口径来源：train.py / feature_version = relative_amplitude_v1
 *     relative = a / max(a.mean(axis=0), 1.0)
 *     delta    = diff(relative, axis=0)
 *     x        = [relative.std(0), mean(|delta|,0), ptp(relative,0), delta.std(0)]
 *     std 为 ddof=0，且用「先求均值、再求平方偏差」的两趟算法与 numpy 对齐。
 *
 * 用法：
 *     CSIInfer.attach(window.CSI_MODEL);              // 或自动 attach
 *     CSIInfer.predict(ampFrames);                    // -> 0..1
 *     CSIInfer.sliceWindows(t, ampFrames);            // -> [{start, score, ...}]
 */
(function (global) {
  'use strict';

  var SC = 64;                 // 子载波数（设备固定 64）
  var WINDOW = 2.0;            // 窗口 2 s
  var TRIM = 1.0;              // 首尾各丢 1 s（避开起始抖动）
  var MIN_FRAMES = 180;        // 一窗最少 180 帧
  var MAX_FRAMES = 220;        // 一窗最多 220 帧
  var MIN_SPAN = 1.9;          // 窗内时间跨度至少 1.9 s
  var MAX_GAP = 0.05;          // 相邻帧最大间隔 50 ms
  var EPS = 1e-8;

  var model = null;
  var meta = null;
  var initError = null;

  /* ------------------------------------------------------------ 初始化 */
  function attach(obj) {
    if (!obj || !obj.trees || !obj.meta) {
      initError = '模型数据缺少 trees / meta';
      return false;
    }
    if (obj.meta.format !== 'csi-forest/v1') {
      initError = '不支持的模型格式：' + obj.meta.format;
      return false;
    }
    if (obj.meta.n_features !== SC * 4) {
      initError = '特征维度异常：期望 ' + (SC * 4) + '，实为 ' + obj.meta.n_features;
      return false;
    }
    model = obj;
    meta = obj.meta;
    initError = null;
    return true;
  }

  function load(url) {
    if (global.CSI_MODEL) return Promise.resolve(attach(global.CSI_MODEL));
    return fetch(url || 'assets/model.json')
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (obj) { return attach(obj); })
      .catch(function (e) { initError = String(e && e.message || e); return false; });
  }

  /* ------------------------------------------------------------ 特征提取 */
  // frames: [[64 个振幅], ...]，至少 2 帧
  function extractFeatures(frames) {
    var F = frames.length;
    if (F < 2) throw new Error('窗口帧数不足：' + F);
    var C = frames[0].length;
    var f, c, v;

    // 1) 逐子载波列均值
    var mean = new Float64Array(C);
    for (f = 0; f < F; f++) {
      var row = frames[f];
      for (c = 0; c < C; c++) mean[c] += row[c];
    }
    for (c = 0; c < C; c++) mean[c] /= F;

    // 2) relative = a / max(mean, 1)
    var rel = new Array(F);
    for (f = 0; f < F; f++) {
      var src = frames[f];
      var out = new Float64Array(C);
      for (c = 0; c < C; c++) out[c] = src[c] / Math.max(mean[c], 1.0);
      rel[f] = out;
    }

    // 3) relative 的均值（std 需要）、极值（ptp 需要）
    var rmean = new Float64Array(C);
    var rmin = new Float64Array(C);
    var rmax = new Float64Array(C);
    for (f = 0; f < F; f++) {
      var rr = rel[f];
      for (c = 0; c < C; c++) {
        v = rr[c];
        rmean[c] += v;
        if (f === 0 || v < rmin[c]) rmin[c] = v;
        if (f === 0 || v > rmax[c]) rmax[c] = v;
      }
    }
    for (c = 0; c < C; c++) rmean[c] /= F;

    // 4) 方差（两趟，ddof=0）
    var rsq = new Float64Array(C);
    for (f = 0; f < F; f++) {
      var rd = rel[f];
      for (c = 0; c < C; c++) {
        var d0 = rd[c] - rmean[c];
        rsq[c] += d0 * d0;
      }
    }

    // 5) delta = diff(relative)，求均值 / 平均绝对 / 标准差
    var D = F - 1;
    var dmean = new Float64Array(C);
    for (f = 0; f < D; f++) {
      var a0 = rel[f], b0 = rel[f + 1];
      for (c = 0; c < C; c++) dmean[c] += b0[c] - a0[c];
    }
    for (c = 0; c < C; c++) dmean[c] /= D;

    var dmad = new Float64Array(C);
    var dsq = new Float64Array(C);
    for (f = 0; f < D; f++) {
      var a1 = rel[f], b1 = rel[f + 1];
      for (c = 0; c < C; c++) {
        var d1 = b1[c] - a1[c];
        dmad[c] += Math.abs(d1);
        var dd = d1 - dmean[c];
        dsq[c] += dd * dd;
      }
    }
    for (c = 0; c < C; c++) {
      dmad[c] /= D;
      dsq[c] /= D;
    }

    // 6) 拼接：[std, mean|delta|, ptp, std(delta)]
    var x = new Float64Array(C * 4);
    for (c = 0; c < C; c++) {
      x[c] = Math.sqrt(Math.max(0, rsq[c] / F));
      x[C + c] = dmad[c];
      x[C * 2 + c] = rmax[c] - rmin[c];
      x[C * 3 + c] = Math.sqrt(Math.max(0, dsq[c]));
    }
    return x;
  }

  /* ------------------------------------------------------------ 森林遍历 */
  function score(x) {
    if (!model) throw new Error(initError || '模型未加载');
    var trees = model.trees;
    var n = trees.length;
    var acc = 0;
    for (var k = 0; k < n; k++) {
      var tr = trees[k];
      var L = tr.left, R = tr.right, Fe = tr.f, T = tr.t, P = tr.p;
      var i = 0;
      while (L[i] !== -1) i = x[Fe[i]] <= T[i] ? L[i] : R[i];
      acc += P[i];
    }
    return acc / n;
  }

  function predict(frames) {
    return score(extractFeatures(frames));
  }

  /* ------------------------------------------------------------ 窗口切分 */
  // t: 秒（相对首帧），amps: 与 t 等长的振幅数组
  // 返回通过质量门槛的窗口，含起止时间、帧数与分数
  function sliceWindows(t, amps, opts) {
    var window = (opts && opts.window) || WINDOW;
    var trim = (opts && opts.trim) || TRIM;
    var n = t.length;
    if (!n) return [];
    var end = t[n - 1];
    var out = [];
    var reject = { count: 0, lowFrames: 0, highFrames: 0, shortSpan: 0, bigGap: 0 };
    var step = 0;

    for (var start = trim; start < end - trim - window + EPS; start = trim + (++step) * window) {
      // t 单调递增，用指针推进代替每次 filter
      var lo = 0;
      while (lo < n && t[lo] < start) lo++;
      var hi = lo;
      while (hi < n && t[hi] < start + window) hi++;
      var count = hi - lo;

      if (count < MIN_FRAMES) { reject.count++; reject.lowFrames++; continue; }
      if (count > MAX_FRAMES) { reject.count++; reject.highFrames++; continue; }
      if (t[hi - 1] - t[lo] < MIN_SPAN) { reject.count++; reject.shortSpan++; continue; }

      var gapBad = false;
      for (var i = lo + 1; i < hi; i++) {
        if (t[i] - t[i - 1] > MAX_GAP) { gapBad = true; break; }
      }
      if (gapBad) { reject.count++; reject.bigGap++; continue; }

      var slice = new Array(count);
      for (var j = 0; j < count; j++) slice[j] = amps[lo + j];

      var s = predict(slice);
      out.push({
        start: start,
        end: start + window,
        frames: count,
        score: s,
        index0: lo,
        index1: hi
      });
    }
    out.reject = reject;
    return out;
  }

  /* ------------------------------------------------------------ 自检 */
  // parity: {windows:[{x, score}], samples:[{amp, ...}]}
  function selfTest(parity) {
    if (!model) return { ok: false, error: initError || '模型未加载' };
    var ws = (parity && parity.windows) || [];
    if (!ws.length) return { ok: false, error: '对拍集为空' };

    var maxScore = 0;
    var flips = 0;
    for (var i = 0; i < ws.length; i++) {
      var got = score(Float64Array.from(ws[i].x));
      var diff = Math.abs(got - ws[i].score);
      if (diff > maxScore) maxScore = diff;
      if ((got >= 0.5) !== (ws[i].score >= 0.5)) flips++;
    }

    // 原始帧 → 特征，验证特征提取本身
    var maxFeat = 0;
    var maxFeatScore = 0;
    var samples = (parity && parity.samples) || [];
    for (var k = 0; k < samples.length; k++) {
      var amp = samples[k].amp;
      var x = extractFeatures(amp);
      var ref = null;
      for (var m = 0; m < ws.length; m++) {
        if (ws[m].file === samples[k].file && Math.abs(ws[m].start_s - samples[k].start_s) < 1e-6) {
          ref = ws[m];
          break;
        }
      }
      if (!ref) continue;
      for (var c = 0; c < x.length; c++) {
        var fd = Math.abs(x[c] - ref.x[c]);
        if (fd > maxFeat) maxFeat = fd;
      }
      maxFeatScore = Math.max(maxFeatScore, Math.abs(score(x) - ref.score));
    }

    return {
      ok: maxScore < 1e-9,
      windows: ws.length,
      maxScoreDiff: maxScore,
      labelFlips: flips,
      samples: samples.length,
      maxFeatureDiff: maxFeat,
      maxSampleScoreDiff: maxFeatScore
    };
  }

  var api = {
    attach: attach,
    load: load,
    extractFeatures: extractFeatures,
    score: score,
    predict: predict,
    sliceWindows: sliceWindows,
    selfTest: selfTest,
    get meta() { return meta; },
    get ready() { return !!model; },
    get error() { return initError; }
  };

  if (global.CSI_MODEL) attach(global.CSI_MODEL);
  global.CSIInfer = api;
})(window);
