/* =========================================================
   实时监控：从 live_bridge.py 的 SSE 流接帧，在浏览器里现场推理

   与回放（replay.js）的区别只在于「帧从哪来」：
     回放：整段 gzip 下载完 → 预先切好所有窗口 → 定时播放
     实时：帧一片片到达 → 滚动缓冲 → 到边界就切一个窗口 → 立刻推理

   切窗口径严格照抄 train.py / infer.js：
     窗口长度 2.0 s，不重叠，开头丢弃 1.0 s（赛题要求丢掉启动段）
     帧数 180–220，跨度 ≥1.9 s，相邻帧间隔 ≤50 ms
   ========================================================= */
(function (global) {
  'use strict';

  var WIN_S = 2.0;
  var TRIM_S = 1.0;
  var MIN_FRAMES = 180;
  var MAX_FRAMES = 220;
  var MIN_SPAN = 1.9;
  var MAX_GAP = 0.05;
  var SC = 64;

  var KEEP_S = 6.0;        // 缓冲里最多留几秒（够切下一个窗口即可）
  var SILENT_MS = 3000;    // 超过这么久没收到帧就提示流静默
  var DEFAULT_URL = 'http://127.0.0.1:9010/events';

  function $(id) { return document.getElementById(id); }

  var el = {};
  var src = null;
  var link = 'idle';       // idle | connecting | live | silent | error | closed

  var ts = [];             // 滚动缓冲：帧时间（秒，相对流起点）
  var amps = [];           // 逐帧 64 维振幅
  var lastT = null;
  var winIdx = 0;          // 下一个待切窗口序号

  var nFrames = 0;         // 累计收帧
  var nWin = 0;            // 成功推理的窗口
  var nRej = 0;            // 被丢弃的窗口
  var rejWhy = {};
  var lastScore = null;
  var lastRecvAt = 0;
  var rateQ = [];          // [时间戳, 帧数] 用于算实时帧率
  var silentTimer = null;
  var autoConnect = false;
  var bridgeUrl = DEFAULT_URL;

  /* ---------------------------------------------------------- 小工具 */
  function setLink(next) {
    link = next;
    var map = {
      idle: ['未连接', ''],
      connecting: ['连接中…', 'warn'],
      live: ['已连接', 'ok'],
      silent: ['流静默', 'warn'],
      error: ['连接失败', 'bad'],
      closed: ['已断开', '']
    };
    var m = map[next] || ['未知', ''];
    if (el.state) {
      el.state.textContent = m[0];
      el.state.dataset.tone = m[1];
    }
    document.body.dataset.link = next;
  }

  function note(text, tone) {
    if (!el.note) return;
    el.note.textContent = text;
    el.note.dataset.tone = tone || '';
  }

  function rate() {
    var now = Date.now();
    while (rateQ.length && rateQ[0][0] < now - 3000) rateQ.shift();
    if (!rateQ.length) return 0;
    var sum = 0;
    for (var i = 0; i < rateQ.length; i++) sum += rateQ[i][1];
    var span = Math.min(3, Math.max(0.5, (now - rateQ[0][0]) / 1000));
    return Math.round(sum / span);
  }

  function paint() {
    if (el.rate) el.rate.textContent = rate() ? rate() + ' Hz' : '—';
    if (el.buf) {
      el.buf.textContent = ts.length
        ? (ts[ts.length - 1] - ts[0]).toFixed(1) + ' s · ' + ts.length + ' 帧'
        : '—';
    }
    if (el.win) el.win.textContent = nWin + ' / ' + nRej;
    if (el.score) {
      el.score.textContent = lastScore === null ? '—' : lastScore.toFixed(3);
      if (lastScore !== null) el.score.dataset.tone = lastScore >= 0.5 ? 'occ' : '';
    }
  }

  /* ---------------------------------------------------------- 缓冲与切窗 */
  function clearBuffer() {
    ts.length = 0;
    amps.length = 0;
    lastT = null;
    winIdx = 0;
  }

  function trimBuffer() {
    var keepFrom = TRIM_S + winIdx * WIN_S - 0.5;
    var k = 0;
    while (k < ts.length && ts[k] < keepFrom) k++;
    if (k > 0) {
      ts.splice(0, k);
      amps.splice(0, k);
    }
  }

  // 第一个 >= v 的下标
  function lowerBound(v) {
    var lo = 0, hi = ts.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (ts[mid] < v) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  function tryWindows() {
    if (lastT === null) return;
    while (lastT >= TRIM_S + (winIdx + 1) * WIN_S) {
      var start = TRIM_S + winIdx * WIN_S;
      var end = start + WIN_S;
      var lo = lowerBound(start);
      var hi = lowerBound(end);
      var count = hi - lo;
      var ok = true;
      var why = '';

      if (count < MIN_FRAMES) { ok = false; why = 'low'; }
      else if (count > MAX_FRAMES) { ok = false; why = 'high'; }
      else if (count > 1 && ts[hi - 1] - ts[lo] < MIN_SPAN) { ok = false; why = 'span'; }
      else {
        for (var i = lo + 1; i < hi; i++) {
          if (ts[i] - ts[i - 1] > MAX_GAP) { ok = false; why = 'gap'; break; }
        }
      }

      if (ok) {
        var slice = new Array(count);
        for (var j = 0; j < count; j++) slice[j] = amps[lo + j];
        var s = global.CSIInfer.predict(slice);
        lastScore = s;
        nWin++;
        global.CSIOcc.pushPrediction(s);
        note('窗口 ' + winIdx + ' [' + start.toFixed(0) + '–' + end.toFixed(0) + ' s] '
          + count + ' 帧 → ' + s.toFixed(3), s >= 0.5 ? 'occ' : '');
      } else {
        nRej++;
        rejWhy[why] = (rejWhy[why] || 0) + 1;
        note('跳过窗口 ' + winIdx + '（' + why + '，' + count + ' 帧）', 'warn');
      }
      winIdx++;
    }
    trimBuffer();
  }

  function ingest(listTs, listAmp) {
    if (!listTs || !listTs.length) return;
    var fresh = [];
    for (var i = 0; i < listTs.length; i++) {
      var a = listAmp[i];
      if (!a || a.length !== SC) continue;
      var t = listTs[i];
      // 样本循环播放时时间戳会回绕，遇到就整段重来
      if (lastT !== null && t < lastT - 0.5) {
        clearBuffer();
      }
      ts.push(t);
      amps.push(a);
      lastT = t;
      fresh.push(a);
    }
    if (!fresh.length) return;

    nFrames += fresh.length;
    rateQ.push([Date.now(), fresh.length]);
    lastRecvAt = Date.now();
    if (link === 'silent') setLink('live');

    if (global.CSIOcc) global.CSIOcc.pushFrames(fresh);
    tryWindows();
    paint();
  }

  /* ---------------------------------------------------------- 连接 */
  function onHello(h) {
    if (h && h.source) {
      note('已连上 ' + h.source + '，等待凑满第一个 2 s 窗口…', '');
    }
  }

  function connect(url) {
    disconnect(true);
    bridgeUrl = url || bridgeUrl;
    if (el.url) el.url.value = bridgeUrl;
    if (!global.EventSource) {
      setLink('error');
      note('当前浏览器不支持 EventSource（Chrome/Edge 60+）。', 'bad');
      return;
    }
    setLink('connecting');
    note('正在连接 ' + bridgeUrl + ' …', '');
    clearBuffer();
    lastRecvAt = Date.now();

    try {
      src = new global.EventSource(bridgeUrl);
    } catch (e) {
      setLink('error');
      note('地址无效：' + bridgeUrl, 'bad');
      return;
    }

    src.onopen = function () {
      setLink('live');
    };

    src.onmessage = function (ev) {
      var payload;
      try {
        payload = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (payload.type === 'hello') {
        onHello(payload);
        return;
      }
      if (payload.type === 'frames') {
        ingest(payload.ts, payload.amp);
      }
    };

    src.onerror = function () {
      if (!src) return;
      // readyState=0 说明浏览器已放弃重连
      if (src.readyState === 2) {
        setLink('error');
        note('连接已关闭，点「连接」重试。桥是否还在运行？', 'bad');
      } else {
        setLink('silent');
        note('连接中断，浏览器正在自动重连…', 'warn');
      }
    };

    if (!silentTimer) {
      silentTimer = setInterval(function () {
        if (link !== 'live') return;
        if (Date.now() - lastRecvAt > SILENT_MS) {
          setLink('silent');
          note('超过 ' + (SILENT_MS / 1000) + ' s 没收到帧，检查设备 / 桥是否还在推流。', 'warn');
        }
      }, 500);
    }
  }

  function disconnect(quiet) {
    if (src) {
      src.onopen = src.onmessage = src.onerror = null;
      try { src.close(); } catch (e) {}
      src = null;
    }
    if (!quiet) {
      setLink('closed');
      note('已断开。', '');
    }
  }

  function hardReset() {
    disconnect(true);
    clearBuffer();
    nFrames = 0;
    nWin = 0;
    nRej = 0;
    rejWhy = {};
    lastScore = null;
    rateQ.length = 0;
    paint();
  }

  /* ---------------------------------------------------------- 对外 */
  function activate() {
    if (global.CSIOcc && document.body.dataset.source !== 'live') {
      global.CSIOcc.setSource('live');
    }
    paint();
    if (!src && autoConnect) connect(bridgeUrl);
    if (!src) {
      note('点「连接」开始接收实时流。默认地址 ' + bridgeUrl, '');
    }
  }

  function deactivate() {
    disconnect(true);
  }

  /* ---------------------------------------------------------- 启动 */
  function boot() {
    el.box = $('liveBox');
    el.url = $('liveUrl');
    el.connect = $('liveConnect');
    el.disconnect = $('liveDisconnect');
    el.state = $('liveState');
    el.rate = $('liveRate');
    el.buf = $('liveBuf');
    el.win = $('liveWin');
    el.score = $('liveScore');
    el.note = $('liveNote');
    if (!el.box) return;

    if (!global.CSIInfer || !global.CSIInfer.ready) {
      setLink('error');
      note('模型未就绪，实时功能不可用。', 'bad');
      if (el.connect) el.connect.disabled = true;
      return;
    }

    var qs = new URLSearchParams(location.search);
    var custom = qs.get('live');
    if (custom) bridgeUrl = custom;
    if (el.url) el.url.value = bridgeUrl;

    if (el.connect) el.connect.addEventListener('click', function () {
      autoConnect = true;
      connect(el.url ? el.url.value.trim() || DEFAULT_URL : bridgeUrl);
    });
    if (el.disconnect) el.disconnect.addEventListener('click', function () {
      autoConnect = false;
      disconnect(false);
      if (global.CSIOcc && document.body.dataset.source === 'live') {
        // 断开后回到模拟流，避免屏幕停在最后一帧的判定上
        var demo = document.querySelector('.src-tab[data-src="demo"]');
        if (demo) demo.click();
      }
    });
    if (el.url) el.url.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { autoConnect = true; connect(el.url.value.trim() || DEFAULT_URL); }
    });

    setLink('idle');
    paint();
    note('点「连接」接收实时流；桥未启动时先运行 _work/live_bridge.py。', '');

    // ?src=live 直接进实时面板并自动连接（自动化测试 / 演示用）
    if (qs.get('src') === 'live') {
      autoConnect = true;
      var tab = document.querySelector('.src-tab[data-src="live"]');
      if (tab) tab.click();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  global.CSILive = {
    connect: connect,
    disconnect: function () { disconnect(false); },
    activate: activate,
    deactivate: deactivate,
    reset: hardReset,
    get link() { return link; },
    get stats() {
      return {
        link: link, frames: nFrames, windows: nWin, rejected: nRej,
        reasons: rejWhy, score: lastScore, buffer: ts.length,
        lastT: lastT, rate: rate(), url: bridgeUrl
      };
    }
  };
})(window);
