/* Plot the complete recorded amplitude series without smoothing. */
(() => {
  function prepare(lines) {
    const entries=lines.map(line=>JSON.parse(line));
    const metadata=entries.find(row=>row.type==='metadata')||{};
    const frames=entries.filter(row=>row.type==='csi');
    if(!frames.length)throw Error('没有可绘制的数据。');
    const first=BigInt(frames[0].device_capture_us);
    const times=frames.map(row=>Number(BigInt(row.device_capture_us)-first)/1e6);
    for(let k=1;k<times.length;k++)if(times[k]<times[k-1])throw Error('设备时间发生回退，无法画出可靠的时间曲线。请保留数据文件检查。');
    if(frames.length>1&&times.at(-1)===0)throw Error('设备时间没有变化，请先检查数据文件。');
    const diffs=times.slice(1).map((t,k)=>t-times[k]).filter(v=>v>0).sort((a,b)=>a-b);
    const gap=Math.max(0.1,5*(diffs[Math.floor(diffs.length/2)]||0));
    const breaks=frames.map((row,k)=>k>0&&(BigInt(row.sequence)!==BigInt(frames[k-1].sequence)+1n||times[k]-times[k-1]>gap));
    let peak=0,n=0;
    for(const row of frames){n=Math.max(n,row.amplitude.length);for(const a of row.amplitude)if(Number.isFinite(a))peak=Math.max(peak,a);}
    return {metadata,frames,times,breaks,n,peak,duration:times.at(-1)};
  }
  async function save(lines) {
    const p=prepare(lines),canvas=document.createElement('canvas');
    canvas.width=2000;canvas.height=1100;
    const ctx=canvas.getContext('2d');
    if(!ctx)throw Error('浏览器无法创建图片画布。');
    const left=110,top=220,width=1770,height=690;
    ctx.fillStyle='#ffffff';ctx.fillRect(0,0,2000,1100);
    ctx.fillStyle='#172c42';ctx.font='bold 36px sans-serif';
    ctx.fillText('原始 CSI 幅度曲线 · 整段记录',left,60);
    ctx.font='22px sans-serif';
    ctx.fillText(`物体：${p.metadata.object||''}    位置：${p.metadata.position||''}    动作：${p.metadata.action||''}`,left,105,1770);
    ctx.fillText(`设备：${p.metadata.device||''}    场地：${p.metadata.room||''}    开始时间：${p.metadata.started_utc||''}`,left,143,1770);
    ctx.fillText(`${p.frames.length} 帧 · ${p.duration.toFixed(3)} 秒 · ${p.n} 个子载波 · 未平滑`,left,181);
    const xmax=p.duration||1,ymax=Math.max(1,Math.ceil(p.peak*1.05));
    ctx.font='20px sans-serif';ctx.lineWidth=1;
    for(let k=0;k<=10;k++){
      const x=left+width*k/10,y=top+height-height*k/10;
      ctx.strokeStyle='#e1e7ed';ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+height);ctx.stroke();
      ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(left+width,y);ctx.stroke();
      ctx.fillStyle='#36485c';ctx.textAlign='center';ctx.fillText((xmax*k/10).toFixed(2),x,top+height+32);
      ctx.textAlign='right';ctx.fillText((ymax*k/10).toFixed(1),left-12,y+7);
    }
    ctx.save();ctx.beginPath();ctx.rect(left,top,width,height);ctx.clip();
    for(let sub=0;sub<p.n;sub++){
      ctx.strokeStyle=`hsla(${240-240*sub/Math.max(1,p.n-1)},75%,43%,0.65)`;
      ctx.lineWidth=1.1;ctx.beginPath();let started=false;
      for(let k=0;k<p.frames.length;k++){
        const value=p.frames[k].amplitude[sub];
        if(!Number.isFinite(value)){started=false;continue;}
        const x=left+width*p.times[k]/xmax,y=top+height-height*value/ymax;
        if(!started||p.breaks[k])ctx.moveTo(x,y);else ctx.lineTo(x,y);
        if(p.frames.length===1){ctx.fillStyle=ctx.strokeStyle;ctx.fillRect(x-2,y-2,4,4);}
        started=true;
      }ctx.stroke();
    }ctx.restore();
    ctx.fillStyle='#172c42';ctx.textAlign='center';ctx.font='24px sans-serif';
    ctx.fillText('距首帧的设备采集时间（秒）',left+width/2,top+height+77);
    ctx.save();ctx.translate(32,top+height/2);ctx.rotate(-Math.PI/2);ctx.fillText('CSI 幅度（硬件数值单位）',0,0);ctx.restore();
    ctx.textAlign='left';ctx.font='20px sans-serif';
    ctx.fillText('蓝 → 红：子载波索引由低到高；零值保留；检测到缺帧或明显时间间隔处断开连线。',left,1030);
    ctx.fillText('静态总览图；精确分析请使用对应 JSONL 数据。',left,1065);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw Error('PNG 图片生成失败。');
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;
    a.download='CSI_'+(p.metadata.session_id||'recording')+'_amplitude.png';
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  window.CSIPageRecorderPlot={prepare,save};
})();
