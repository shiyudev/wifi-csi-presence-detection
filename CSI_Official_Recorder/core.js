/* CSI recording data model, 2026-10-20. */
(() => {
  'use strict';
  function decode(frame, receivedMs) {
    const bytes=frame.record;
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    if(bytes.length<64 || view.getUint16(0,true)!==0x4353 || view.getUint8(2)!==8 || view.getUint8(3)!==64)
      throw Error('Unsupported CSI record version; recording stopped.');
    const n=view.getUint16(10,true), size=view.getUint16(12,true);
    if(n<1 || n>256 || size!==n*2 || bytes.length!==64+size)throw Error('Invalid CSI payload.');
    const i=[],q=[],amplitude=[],phase=[];
    for(let k=0;k<n;k++){
      const imag=view.getInt8(64+2*k),real=view.getInt8(65+2*k);
      i.push(real);q.push(imag);amplitude.push(Math.hypot(real,imag));phase.push(Math.atan2(imag,real));
    }
    const rssi=view.getInt8(43),noise=view.getInt8(44);
    return {type:'csi',sequence:String(frame.streamSequence),browser_received_epoch_ms:receivedMs,
      device_capture_us:String(view.getBigUint64(22,true)),subcarrier_count:n,
      i,q,amplitude,phase_rad:phase,rssi_dbm:rssi,noise_floor_dbm:noise,snr_db:noise<0?rssi-noise:null,
      fresh_total:String(frame.freshRecordTotal),device_drop_total:String(frame.rawDropTotal),
      backpressure_total:String(frame.sendBackpressureTotal),
      raw_csi_v8_base64:btoa(String.fromCharCode(...bytes))};
  }
  class Recording {
    constructor(metadata,maxBytes=20*1024*1024){
      this.lines=[];this.bytes=0;this.maxBytes=maxBytes;this.count=0;this.lastSeq=null;this.lastTime=null;
      this.active=true;this.ended=false;this.error='';
      this.put({type:'metadata',schema_version:1,source:'espectre.dev_real_CSI_V8',
        started_utc:new Date().toISOString(),session_id:crypto.randomUUID(),
        ...metadata,label_verified:false});
    }
    put(obj){const line=JSON.stringify(obj)+'\n';const size=new TextEncoder().encode(line).length;
      if(this.bytes+size>this.maxBytes)throw Error('已达到 20 MB 记录上限，请导出后新开一段。');
      this.lines.push(line);this.bytes+=size;
    }
    accept(frame,receivedMs=Date.now()){
      if(!this.active)return;
      try {
        const row=decode(frame,receivedMs),seq=BigInt(row.sequence);
        if(this.lastSeq!==null && seq<=this.lastSeq)throw Error('设备数据流重启或序号回退，请导出后新开一段。');
        this.put(row);this.lastSeq=seq;this.lastTime=row.device_capture_us;this.count++;
      }catch(e){this.active=false;this.error=e.message;}
    }
    mark(note){if(!this.active)return;
      try{this.put({type:'event',note,browser_epoch_ms:Date.now(),latest_sequence:this.lastSeq===null?null:String(this.lastSeq),latest_device_capture_us:this.lastTime});}
      catch(e){this.active=false;this.error=e.message;}
    }
    finish(){
      if(this.ended)return;this.active=false;this.ended=true;
      // Keep final status even if the data limit has been reached.
      this.lines.push(JSON.stringify({type:'summary',ended_utc:new Date().toISOString(),
        saved_records:this.count,status:this.error?'error':this.count?'complete':'empty',detail:this.error})+'\n');
    }
  }
  window.CSIPageRecorderCore={Recording,decode};
})();
