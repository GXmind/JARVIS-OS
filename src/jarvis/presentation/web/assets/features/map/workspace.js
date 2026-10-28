import {orbitView,panView,zoomView,VIEW_KEYS} from "./controls.js";
const STATE_KEYS=["mapOpen","mapReady","mapStage","mapStatus","mapTrip","mapSummary","cityScene","cityView","cityExtent","cityBrowseExtent","cityFocus","cityFrame","cityHeightScale",...VIEW_KEYS];
export function mapSnapshot(n){
 const state=Object.fromEntries(STATE_KEYS.map(key=>[key,n.state[key]??null]));
 return {state,command:n.command||{},options:n.options||[],selected:n.selected||null,resolved:n.resolved||null,
  labels:Object.fromEntries(["travelOriginSource","travelOrigin","travelDestination","resolvedOrigin","resolvedDestination","cityViewLabel","cityDataNote"].map(id=>[id,document.getElementById(id)?.textContent||""]))};
}
export class MapWorkspaceClient{
 constructor({api,state,getNavigation,message}){
  Object.assign(this,{api,state,getNavigation,message});this.structure="";this.view="";this.running=true;this.sending=false;this.opening=false;this.started=0;this.handledEpoch=-1;this.remote={requested:false};this.tick();
 }
 async tick(){
  try{
   const data=await this.api("map/workspace");this.remote=data;
   document.getElementById("mapReturn").hidden=!data.requested;
   document.getElementById("mapDetach").textContent=data.requested?"副屏地图独立运行":"手势传送到另一屏";
   document.getElementById("handTargetMap").disabled=!data.requested;
   const n=await this.getNavigation();
   if(data.detached&&this.transferSource&&this.handledEpoch!==data.epoch){
    this.handledEpoch=data.epoch;
    const source=this.transferSource;
    this.state.mapTransfer={phase:"depart",started:performance.now(),duration:1900,direction:data.direction,source:source.state};
    if((n.command?.id||0)===(source.command?.id||0)&&n.isOpen)n.close();
    document.getElementById("handTarget").value="map";
    this.message("地图已化作粒子传往副屏；副屏内容独立保留。",false,5);
   }
   if(data.requested&&!data.detached&&(data.window?.error||this.started&&Date.now()-this.started>24000)){
    await this.api("map/close",{});this.message(data.window?.error||"地图窗口连接超时，地图保留在主窗口。",true);this.started=0;
   }
   if(!data.requested&&document.getElementById("handTarget").value==="map")document.getElementById("handTarget").value="primary";
   await this.publish(n);
  }catch(error){this.lastError=error.message;}
  if(this.running)this.timer=setTimeout(()=>this.tick(),160);
 }
 async publish(n,force=false){
  if(force)while(this.sending)await new Promise(resolve=>setTimeout(resolve,20));
  if(this.sending)return;
  const s=this.state,structure=[n.isOpen,s.mapReady,s.mapStage,s.mapStatus,s.mapSummary,s.mapTrip,s.cityRevision,n.selected,n.command?.id,n.options?.length].join("|");
  const view=Object.fromEntries([...VIEW_KEYS,"cityHeightScale"].map(key=>[key,Number(s[key])||(key==="cityPitch"?.62:key==="cityZoom"?1:key==="cityHeightScale"?16:0)]));
  const encoded=JSON.stringify(view);this.sending=true;
  try{
   if(force||structure!==this.structure){const result=await this.api("map/publish",{...mapSnapshot(n),base_revision:this.remote.revision||0});this.remote.revision=result.revision;this.structure=structure;this.view=encoded;}
   else if(encoded!==this.view){await this.api("map/view",{view});this.view=encoded;}
  }finally{this.sending=false;}
 }
 async detach(direction){
  if(this.opening)return;
  if(this.remote.requested){this.message("副屏地图独立运行；请在副屏关闭后再传送新地图。");return;}
  this.opening=true;
  try{
   const n=await this.getNavigation();if(!n.state.mapReady)throw new Error("请先加载主屏地图，再用张掌横划传送。");
   await this.publish(n,true);this.transferSource=JSON.parse(JSON.stringify(mapSnapshot(n)));this.started=Date.now();
   const value=document.getElementById("mapDisplay").value;
   const data=await this.api("map/detach",{...(value==="auto"?{}:{display:Number(value)}),direction});
   this.message(data.multiple_displays?"正在另一块屏幕建立粒子接收场…":"当前检测到一块屏幕，先在独立窗口演示粒子传送。");
  }catch(error){this.message(error.message,true);}finally{this.opening=false;}
 }
 async closeRemote(){try{await this.api("map/close",{});}catch(error){this.message(error.message,true);}}
 async gesture(action){
  if(!document.getElementById("settingsLayer").hidden||!document.getElementById("command").hidden||!document.getElementById("exitLayer").hidden)return;
  if(action.type==="handoff"){await this.detach(action.direction);return;}
  if(document.getElementById("handTarget").value==="map"){
   if(this.remote.detached)await this.api("map/gesture",{epoch:this.remote.epoch,action});return;
  }
  if(!this.state.mapReady)return;
  const n=await this.getNavigation();
  if(action.type==="pan")panView(this.state,action.dx*innerWidth,action.dy*innerHeight);
  else if(action.type==="orbit")orbitView(this.state,action.dx*innerWidth,action.dy*innerHeight);
  else if(action.type==="zoom")zoomView(this.state,-Math.log(action.factor)*1000);
  else if(action.type==="end"&&action.commit)n.commitView();
 }
 stop(){this.running=false;clearTimeout(this.timer);}
}
