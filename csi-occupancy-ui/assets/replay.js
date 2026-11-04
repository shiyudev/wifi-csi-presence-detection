/*!
 * replay.js — 真实采集帧回放（浏览器内推理）
 *
 * 数据来源：
 *   1) data/index.json 里的样本（原始 jsonl 的 gzip，需 http 打开）
 *   2) 用户本地选择的 .jsonl / .jsonl.gz（file:// 打开时也能用）
 *
 * 流程：gzip 流式解压 → 逐行解析 csi 帧 → 由 I/Q 算振幅 → 按 1 s/1 s 实时喂给
 *      CSIOcc.pushFrames，并在每个 2 s 窗口收满时用 CSIInfer 算分数推给大屏。
 * 全程没有后端、没有 WASM，模型就是 200 棵树的 JSON。
 */
(function (global) {
  'use strict';

  var DECIMATE = 2;          // 热力图按 2:1 抽帧显示（推理始终用全帧）
  var STEP_MS = 40;          // 播放调度间隔

  var el = {};
  var samples = [];
  var cur = null;            // {name, label, note, frames, windows, dur}
  var timer = null;
  var idx = 0;               // 已消费的帧下标
  var wi = 0;                // 已发出的窗口下标
  var startedAt = 0;         // 播放起点（performance.now 基准）
  var pos = 0;               // 已播放秒数

  function $(id) { return document.getElementById(id); }

  function setNote(text, tone) {
    if (!el.note) return;
    el.note.textContent = text;
    el.note.dataset.tone = tone || '';
  }

  /* ---------------------------------------------------------- 解析 */
  function gunzip(stream) {
    if (!('DecompressionStream' in global)) {
      throw new Error('当前浏览器不支持 DecompressionStream（需 Chrome/Edge 80+）');
    }
    return stream.pipeThrough(new global.DecompressionStream('gzip'));
  }

  function parseStream(stream) {
    if (!('TextDecoderStream' in global)) {
      return Promise.reject(new Error('当前浏览器不支持 TextDecoderStream'));
    }
    var reader = stream.pipeThrough(new global.TextDecoderStream()).getReader();
    var buf = '';
    var meta = null;
    var frames = [];
    var t0 = null;

    function eat(line) {
      if (!line) return;
      var o;
      try { o = JSON.parse(line); } catch (e) { return; }
      if (o.type === 'metadata') { meta = o; return; }
      if (o.type !== 'csi' || !o.i || !o.q) return;
      var us = Number(o.device_capture_us);
      if (!isFinite(us)) return;
      if (t0 === null) t0 = us;
      var n = o.i.length;
      var amp = new Float64Array(n);
      for (var c = 0; c < n; c++) {
        var iv = o.i[c], qv = o.q[c];
        amp[c] = Math.sqrt(iv * iv + qv * qv);
      }
      frames.push({ t: (us - t0) / 1e6, amp: amp });
    }

    function pump() {
      return reader.read().then(function (r) {
        if (r.done) {
          if (buf.trim()) eat(buf.trim());
          return { meta: meta, frames: frames };
        }
        buf += r.value;
        var at;
        while ((at = buf.indexOf('\n')) >= 0) {
          eat(buf.slice(0, at).trim());
          buf = buf.slice(at + 1);
        }
        if (el.fill && cur === null) {
          // 解析阶段没有总字节数，只能用帧数递增表示进度
          el.fill.style.width = Math.min(96, frames.length / 30) + '%';
        }
        return pump();
      });
    }
    return pump();
  }

  /* ---------------------------------------------------------- 装载 */
  function adopt(name, label, note, parsed) {
    var frames = parsed.frames;
    if (frames.length < 200) {
      throw new Error('帧数太少（' + frames.length + '），无法切出 2 s 窗口');
    }
    var t = new Float64Array(frames.length);
    var amps = new Array(frames.length);
    for (var i = 0; i < frames.length; i++) { t[i] = frames[i].t; amps[i] = frames[i].amp; }

    var windows = global.CSIInfer.sliceWindows(t, amps);
    if (!windows.length) throw new Error('整段数据没有窗口通过质量门槛');

    cur = {
      name: name,
      label: label,
      note: note,
      frames: frames,
      windows: windows,
      dur: frames[frames.length - 1].t
    };

    var meta = parsed.meta || {};
    var occWin = windows.filter(function (w) { return w.score >= 0.5; }).length;
    setNote(
      cur.note + '　' + frames.length + ' 帧 / ' + cur.dur.toFixed(1) + ' s　'
      + windows.length + ' 个窗口通过门槛（判有人 ' + occWin + ' 个）'
      + (meta.room ? '　房间 ' + meta.room : ''),
      ''
    );
    el.toggle.disabled = false;
    el.toggle.textContent = '播放';
    reset(false);
    updateFill(0);
  }

  function loadSample(entry) {
    stop();
    setNote('正在载入 ' + entry.file + ' …', '');
    cur = null;
    return fetch('data/' + entry.file, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return parseStream(gunzip(r.body));
      })
      .then(function (parsed) {
        adopt(entry.file, entry.label, entry.note || '', parsed);
      })
      .catch(function (e) {
        setNote('载入失败：' + (e && e.message || e)
          + '（file:// 打开时请用下方「选择本地文件」）', 'bad');
        el.toggle.disabled = true;
      });
  }

  function loadFile(file) {
    stop();
    setNote('正在解析本地文件 ' + file.name + ' …', '');
    cur = null;
    var stream = file.stream();
    if (/\.gz$/i.test(file.name)) stream = gunzip(stream);
    return parseStream(stream)
      .then(function (parsed) {
        adopt(file.name, null, '本地文件', parsed);
      })
      .catch(function (e) {
        setNote('解析失败：' + (e && e.message || e), 'bad');
        el.toggle.disabled = true;
      });
  }

  /* ---------------------------------------------------------- 播放 */
  function updateFill(p) {
    if (el.fill) el.fill.style.width = (Math.max(0, Math.min(1, p)) * 100).toFixed(1) + '%';
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    if (el.toggle) el.toggle.textContent = '播放';
  }

  function reset(withSource) {
    stop();
    idx = 0;
    wi = 0;
    pos = 0;
    if (withSource !== false) updateFill(0);
  }

  function play() {
    if (!cur || timer) return;
    if (idx >= cur.frames.length) reset(false);
    global.CSIOcc.setTruth(cur.label !== null ? cur.label === 1 : null);
    if (cur.label === null) {
      global.CSIOcc.setTruth(false);
      var ht = document.getElementById('heroTruth');
      if (ht) ht.textContent = '回放真值 · 未标注';
    }
    startedAt = global.performance.now() - pos * 1000;
    timer = setInterval(step, STEP_MS);
    el.toggle.textContent = '暂停';
  }

  function step() {
    if (!cur) return;
    var elapsed = (global.performance.now() - startedAt) / 1000;
    var n = cur.frames.length;
    var batch = [];
    var pushed = 0;

    while (idx < n && cur.frames[idx].t <= elapsed) {
      var f = cur.frames[idx++];
      if (pushed++ % DECIMATE === 0) batch.push(f.amp);
    }
    if (batch.length) global.CSIOcc.pushFrames(batch);

    // 窗口收满即出分：模拟设备每 2 s 吐一个判决
    while (wi < cur.windows.length && cur.windows[wi].index1 <= idx) {
      global.CSIOcc.pushPrediction(cur.windows[wi].score);
      wi++;
    }

    pos = elapsed;
    updateFill(idx / n);

    if (idx >= n) {
      stop();
      updateFill(1);
      var occWin = cur.windows.filter(function (w) { return w.score >= 0.5; }).length;
      setNote('播放结束：' + cur.windows.length + ' 个窗口，判有人 ' + occWin
        + ' 个。分数由浏览器内随机森林现算。', 'ok');
      el.toggle.textContent = '重播';
    }
  }

  /* ---------------------------------------------------------- UI */
  function switchSource(mode) {
    Array.prototype.forEach.call(el.tabs.children, function (b) {
      b.classList.toggle('active', b.dataset.src === mode);
    });
    el.box.hidden = mode !== 'replay';
    var liveBox = document.getElementById('liveBox');
    if (liveBox) liveBox.hidden = mode !== 'live';
    var aside = document.querySelector('.sidebar');
    if (aside) aside.classList.toggle('replaying', mode === 'replay' || mode === 'live');
    global.CSIOcc.setSource(mode);
    if (global.CSILive) {
      if (mode === 'live') global.CSILive.activate();
      else global.CSILive.deactivate();
    }
    if (mode === 'replay' && !cur && samples.length) {
      var first = el.pick.options[el.pick.selectedIndex];
      if (first && first.value) return loadSample(samples[Number(first.value)]);
    }
    if (mode === 'demo') {
      stop();
      var ht = document.getElementById('heroTruth');
      if (ht) ht.textContent = '演示真值 · 无人';
    }
    return null;
  }

  function initSamples() {
    return fetch('data/index.json', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        samples = (d && d.samples) || [];
        if (!samples.length) return;
        el.pick.innerHTML = samples.map(function (s, i) {
          return '<option value="' + i + '">' + s.source.replace(/\.jsonl$/, '')
            + '（' + s.durationSec + 's）</option>';
        }).join('');
        el.pick.disabled = false;
      })
      .catch(function () {
        el.pick.innerHTML = '<option value="">（样本需通过 http 打开）</option>';
        el.pick.disabled = true;
      });
  }

  function boot() {
    el.tabs = $('srcTabs');
    el.box = $('replayBox');
    el.pick = $('replayPick');
    el.toggle = $('replayToggle');
    el.reset = $('replayReset');
    el.file = $('replayFile');
    el.fill = $('replayFill');
    el.note = $('replayNote');
    if (!el.tabs || !global.CSIOcc) return;

    if (!global.CSIInfer || !global.CSIInfer.ready) {
      var why = global.CSIInfer ? global.CSIInfer.error : 'infer.js 未加载';
      setNote('模型未就绪：' + why + '，回放不可用。', 'bad');
      el.toggle.disabled = true;
      return;
    }

    el.tabs.addEventListener('click', function (ev) {
      var b = ev.target.closest('.src-tab');
      if (b && b.dataset.src) switchSource(b.dataset.src);
    });

    el.toggle.addEventListener('click', function () {
      if (!cur) return;
      if (timer) { stop(); return; }
      play();
    });

    el.reset.addEventListener('click', function () {
      if (!cur) return;
      reset(true);
      global.CSIOcc.setSource('replay');
      setNote(cur.note + '　已重置，点「播放」从头开始。', '');
    });

    el.pick.addEventListener('change', function () {
      var i = Number(el.pick.value);
      if (samples[i]) loadSample(samples[i]);
    });

    el.file.addEventListener('change', function () {
      var f = el.file.files && el.file.files[0];
      if (f) loadFile(f);
    });

    el.toggle.disabled = true;
    initSamples().then(function () {
      var qs = new URLSearchParams(location.search);
      // ?sample=N 选第 N 段样本（自动化测试用）
      var pick = qs.get('sample');
      if (pick !== null && samples[Number(pick)]) el.pick.value = String(Number(pick));
      if (qs.get('src') !== 'replay') return null;
      // ?src=replay          打开即切到回放并载入首个样本
      // ?src=replay&play=1   载入后自动播放（自动化测试用）
      return Promise.resolve(switchSource('replay')).then(function () {
        if (qs.get('play') === '1' && cur) play();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  global.CSIReplay = { play: play, stop: stop, reset: reset, loadFile: loadFile,
                       get current() { return cur; } };
})(window);
