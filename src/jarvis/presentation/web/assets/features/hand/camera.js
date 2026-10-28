import {HandInterpreter} from "./gestures.js";
const CONNECTIONS=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
export class HandCamera{
 constructor({api,onAction,onStatus,video,overlay}){
  this.api=api;this.onAction=onAction;this.onStatus=onStatus;this.video=video;this.overlay=overlay;
  this.engine=new HandInterpreter();this.generation=0;this.active=false;this.worker=null;this.stream=null;this.inflight=false;this.timer=null;this.frameRequest=null;
  this.visibility=()=>{if(document.hidden&&this.active){this.stop();onStatus("主窗口隐藏，摄像头已关闭");}};
  document.addEventListener("visibilitychange",this.visibility);addEventListener("pagehide",()=>this.stop());
 }
 async start(){
  if(this.active)return;
  const generation=++this.generation;this.active=true;this.onStatus("正在准备本机手势识别…");
  try{
   const runtime=await this.api("hand/status");if(generation!==this.generation)return;if(!runtime.ready)throw new Error(runtime.message);
   if(!navigator.mediaDevices?.getUserMedia)throw new Error("浏览器不支持摄像头，请使用已更新的 Edge。");
   const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{width:{ideal:480},height:{ideal:360},frameRate:{ideal:15,max:20}}});
   if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());return;}
   this.stream=stream;for(const track of stream.getVideoTracks())track.onended=()=>{if(generation===this.generation&&this.active)this.fail("摄像头连接已断开。");};this.video.srcObject=stream;await this.video.play();
   if(generation!==this.generation)return;
   await new Promise((resolve,reject)=>{
    this.cancelInit=reject;
    const worker=this.worker=new Worker(new URL("./worker.js",import.meta.url));
    this.timer=setTimeout(()=>reject(new Error("本机识别器启动超时。")),25000);
    worker.onerror=()=>reject(new Error("手势后台线程启动失败。"));
    worker.onmessage=event=>{
     if(event.data.type==="ready"){this.cancelInit=null;clearTimeout(this.timer);this.timer=null;resolve();}
     else if(event.data.type==="error")reject(new Error(event.data.message));
    };worker.postMessage({type:"init"});
   });
   if(generation!==this.generation)return;
   this.worker.onerror=()=>{if(generation===this.generation)this.fail("手势后台线程中断。");};
   this.worker.onmessage=event=>{
    if(generation!==this.generation)return;
    clearTimeout(this.timer);this.timer=null;this.inflight=false;
    if(event.data.type==="error"){this.fail("手势识别失败："+event.data.message);return;}
    if(event.data.type!=="result")return;
    const hands=event.data.landmarks;this.paint(hands);
    this.onStatus(hands.length?"已跟踪 "+hands.length+" 只手 · "+Math.round(event.data.milliseconds)+" ms":"等待手进入画面");
    for(const action of this.engine.update(hands,performance.now()))this.onAction(action);
   };
   this.engine.reset();this.lastFrame=-1;this.lastStamp=0;
   const loop=async stamp=>{
    if(!this.active||generation!==this.generation)return;
    this.frameRequest=requestAnimationFrame(loop);
    if(this.inflight||stamp-this.lastStamp<100||this.video.currentTime===this.lastFrame)return;
    this.inflight=true;this.lastStamp=stamp;this.lastFrame=this.video.currentTime;
    try{
     const bitmap=await createImageBitmap(this.video,{resizeWidth:480,resizeHeight:360});
     if(!this.active||generation!==this.generation){bitmap.close();return;}
     this.timer=setTimeout(()=>this.fail("手势识别响应超时，摄像头已关闭。"),3500);
     this.worker.postMessage({type:"frame",bitmap,timestamp:stamp},[bitmap]);
    }catch(error){if(generation===this.generation)this.fail("摄像头画面读取失败。");}
   };
   this.frameRequest=requestAnimationFrame(loop);
  }catch(error){
   if(generation!==this.generation)return;
   const names={NotAllowedError:"摄像头权限未允许，请在 Edge 中允许本机页面访问。",NotFoundError:"没有找到摄像头。",NotReadableError:"摄像头可能被其他软件占用。"};
   this.stop();this.onStatus(names[error.name]||error.message,true);
  }
 }
 fail(message){this.stop();this.onStatus(message,true);}
 stop(){
  if(this.engine.mode==="pan"||this.engine.mode==="zoom")this.onAction({type:"end",commit:true});
  ++this.generation;this.active=false;const cancel=this.cancelInit;this.cancelInit=null;cancel?.(new Error("摄像头已关闭。"));cancelAnimationFrame(this.frameRequest);clearTimeout(this.timer);this.timer=null;
  this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;this.video.srcObject=null;
  this.worker?.terminate();this.worker=null;this.inflight=false;this.engine.reset();
  this.overlay.getContext("2d").clearRect(0,0,this.overlay.width,this.overlay.height);
 }
 paint(hands){
  const canvas=this.overlay,ctx=canvas.getContext("2d");if(canvas.width!==480)canvas.width=480;if(canvas.height!==360)canvas.height=360;ctx.clearRect(0,0,480,360);ctx.strokeStyle="#9deaff";ctx.fillStyle="#e1fbff";ctx.lineWidth=1.8;
  for(const hand of hands){for(const [a,b]of CONNECTIONS){ctx.beginPath();ctx.moveTo((1-hand[a].x)*480,hand[a].y*360);ctx.lineTo((1-hand[b].x)*480,hand[b].y*360);ctx.stroke();}
   for(const point of hand){ctx.beginPath();ctx.arc((1-point.x)*480,point.y*360,2.2,0,Math.PI*2);ctx.fill();}}
 }
}
