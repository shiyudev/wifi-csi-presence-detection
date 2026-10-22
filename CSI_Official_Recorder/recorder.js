/* Unofficial read-only recorder for the official page's already-authorized stream. */
(() => {
  'use strict';
  if(window.__csiPageRecorderInstalled)return;
  window.__csiPageRecorderInstalled=true;
  let recording=null,downloadRequested=false,hooked=false,lastFrameAt=0,ui=null;
  const tag=Symbol('csi-recording-hook');
  function attach(){
    const proto=window.ESPectreRawCsiParser?.prototype;
    if(!proto || typeof proto.append!=='function')return;
    if(proto.append[tag]){hooked=true;return;}
    const original=proto.append;
    function append(...args){
      const frames=original.apply(this,args);
      if(frames.length)lastFrameAt=Date.now();
      if(recording?.active)for(const frame of frames)recording.accept(frame);
      return frames;
    }
    append[tag]=true;proto.append=append;hooked=true;
  }
  function mount(){
    if(ui || !document.body)return;
    const host=document.createElement('div');document.body.append(host);
    const root=host.attachShadow({mode:'open'});
    root.innerHTML=`<style>
      :host{position:fixed;right:16px;bottom:16px;z-index:2147483647;font:14px/1.5 system-ui;color:#172c42}
      details{width:335px;max-height:85vh;overflow:auto;box-sizing:border-box;background:white;border:2px solid #2866b8;border-radius:12px;padding:14px;box-shadow:0 4px 20px #0003}
      summary{font-weight:bold;cursor:pointer}label{display:block;margin-top:7px}input,select{box-sizing:border-box;width:100%;padding:6px;border:1px solid #acbccc;border-radius:5px;background:white;color:#152238}
      button{margin:8px 4px 0 0;padding:7px 10px;cursor:pointer}button:disabled{cursor:default}p{margin:10px 0}small{color:#526678}
    </style><details open><summary>原始 CSI 记录器 · 官网版</summary>
    <p>先连接设备并启动官网原始曲线，再点击开始记录。</p>
    <label>物体<input id="object" placeholder="人 / 风扇 / 空场"></label>
    <label>位置<input id="position" placeholder="P1：连线中点"></label>
    <label>动作<input id="action" placeholder="走动 / 转动 / 静止"></label>
    <label>设备 ID<input id="device" placeholder="例如：1e1bb9"></label>
    <label>场地<input id="room" value="6B514"></label>
    <label>视频文件名（可选）<input id="video"></label>
    <label>实验标签<select id="label"><option value="unlabeled">待视频标注</option><option value="motion">有运动（待核对）</option><option value="no_motion">无运动（待核对）</option></select></label>
    <button id="start">开始记录</button><button id="stop" disabled>停止记录</button><button id="export" disabled>导出数据</button><button id="png" disabled>保存曲线图片</button>
    <label>事件备注<input id="note" placeholder="开始运动 / 停止运动"></label><button id="mark" disabled>标记事件</button>
    <p id="status" role="status">等待官网加载数据解析器……</p>
    <small>文件导出前暂存在内存；刷新或关闭页面会丢失。每段上限 20 MB。不会上传云端。</small>
    </details>`;
    const el=id=>root.getElementById(id);ui={el};
    el('start').onclick=()=>{
      if(recording&&!downloadRequested){alert('请先导出上一段记录，再开始新的一段。');return;}
      if(!hooked || Date.now()-lastFrameAt>3000){alert('未收到实时 CSI。请先在官网连接真实设备并点击 Start，确认曲线运行。');return;}
      const metadata={};for(const k of ['object','position','action','device','room','video'])metadata[k]=el(k).value.trim();
      for(const k of ['object','position','action','device'])if(!metadata[k]){alert('请填写物体、位置、动作和设备 ID。');return;}
      metadata.initial_label=el('label').value;
      recording=new window.CSIPageRecorderCore.Recording(metadata);downloadRequested=false;render();
    };
    el('png').onclick=async()=>{
      if(!recording?.count)return;
      recording.finish();render();
      try{await window.CSIPageRecorderPlot.save(recording.lines);}catch(e){alert('图片保存失败：'+e.message);}
    };
    el('stop').onclick=()=>{recording?.finish();render();};
    el('mark').onclick=()=>{if(recording?.active){recording.mark(el('note').value);el('note').value='';render();}};
    el('export').onclick=()=>{
      if(!recording)return;recording.finish();
      const blob=new Blob(recording.lines,{type:'application/x-ndjson;charset=utf-8'}),url=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=url;
      a.download='CSI_'+JSON.parse(recording.lines[0]).session_id+'.jsonl';
      document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      downloadRequested=true;render();
    };
  }
  function render(){
    if(!ui)return;const {el}=ui;const active=!!recording?.active;
    el('start').disabled=active||!hooked||!!(recording&&!downloadRequested);
    el('png').disabled=!recording?.count;
    el('stop').disabled=!active;el('export').disabled=!recording;el('mark').disabled=!active;
    if(!recording){el('status').textContent=hooked?(Date.now()-lastFrameAt<3000?'已收到真实 CSI，可以开始记录。':'记录器已就绪，等待官网的真实 CSI 数据。'):'等待官网数据解析器。若长期不变，官网接口可能已更新。';return;}
    const stale=active&&Date.now()-lastFrameAt>3000?' 最近 3 秒未收到数据，请检查原始曲线。':'';
    el('status').textContent=`${active?'记录中':'已停止'}：${recording.count} 帧，约 ${(recording.bytes/1024/1024).toFixed(2)} MB。${recording.error||''}${stale}${downloadRequested?' 已请求下载，请到下载文件夹确认文件。':''}`;
  }
  setInterval(()=>{attach();mount();render();},250);
  window.addEventListener('beforeunload',e=>{if(recording&&!downloadRequested){e.preventDefault();e.returnValue='';}});
})();
