import {createClient} from "./core/client.js";
import {createVisual} from "./rendering/energy.js";
import {NavigationController} from "./features/navigation/controller.js";
import {bindMapControls,orbitView,panView,zoomView} from "./features/map/controls.js";
const $=id=>document.getElementById(id),api=createClient(window.JARVIS_TOKEN);
const state={phase:"initial",level:0,mapOnly:true,mapReady:false},metrics=window.__sceneMetrics={frames:0,ready:false};
const message=text=>{$("replicaStatus").textContent=text;};
const n=window.__navigation=new NavigationController({api,state,message,openSettings:()=>message("连接和语音设置位于主窗口。")});
window.__mapReplica={state,metrics,navigation:n};
const visual=createVisual($("space"),state,metrics);visual.setLowQuality(true);
let revision=-1,epoch=0,after=0,readyEpoch=-1,stopped=false;
bindMapControls($("space"),state,{onViewEnd:()=>n.commitView(),onZoom:()=>n.scheduleViewCommit()});
function receive(snapshot,direction){
 n.close();Object.assign(state,snapshot.state);state.mapOnly=true;state.cityParticleBudget=16000;state.cityRevision=(state.cityRevision||0)+1;
 n.command=snapshot.command||{};n.options=snapshot.options||[];n.selected=snapshot.selected;n.resolved=snapshot.resolved;
 n.path=state.cityScene?.path||[];n.currentContext=state.cityScene?.context||{};
 n.config={city:n.command.city||"苏州",view_meters:state.cityExtent||1600,height_scale:state.cityHeightScale||16};
 n.isOpen=true;n.panel.hidden=false;n.stage.hidden=false;document.body.classList.add("map-open","map-active");
 for(const [id,text]of Object.entries(snapshot.labels||{}))if($(id))$(id).textContent=text;
 n.renderOptions();n.updateFrame();$("cityHeight").value=state.cityHeightScale||16;$("cityHeightValue").textContent="×"+(state.cityHeightScale||16);
 state.mapTransfer={phase:"arrive",started:performance.now()+120,duration:2200,direction:{x:-(direction?.x??1),y:-(direction?.y??0)}};
}
function cameraAction(action){
 if(!state.mapReady)return;
 if(action.type==="pan")panView(state,action.dx*innerWidth,action.dy*innerHeight);
 else if(action.type==="orbit")orbitView(state,action.dx*innerWidth,action.dy*innerHeight);
 else if(action.type==="zoom")zoomView(state,-Math.log(action.factor)*1000);
 else if(action.type==="end")n.commitView();
}
async function poll(){
 if(stopped)return;
 try{
  const data=await api("map/workspace?since="+revision+"&after="+after);epoch=data.epoch;
  if(data.requested&&data.snapshot){receive(data.snapshot,data.direction);revision=data.transfer_revision;after=0;}
  if(data.requested&&state.mapReady&&metrics.ready&&readyEpoch!==epoch){await api("map/ready",{epoch,revision});readyEpoch=epoch;}
  for(const action of data.commands||[]){if(action.sequence>after){cameraAction(action);after=action.sequence;}}
  if(!data.requested){if(n.isOpen)n.close();message("此地图窗口已结束");}
  else if(!state.mapTransfer||metrics.transferProgress>=1)message("独立地图 · 主屏对话与新任务不会改变此处内容");
  $("replicaSummary").textContent=state.mapSummary||state.mapTrip||"";
 }catch(error){message("本机数据服务暂时中断，当前地图保留："+error.message);}
 if(!stopped)setTimeout(poll,160);
}
async function closeMap(){n.close();try{await api("map/close",{epoch});}catch(error){message(error.message);}}
$("returnPrimary").onclick=closeMap;
addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();closeMap();}if(event.key==="F8"||event.key==="F9"||event.key==="Enter"){event.preventDefault();message("语音和摄像头输入仅在主窗口；此地图可以独立关闭。");}});
addEventListener("pagehide",()=>{stopped=true;n.close();visual.stop();fetch("/api/map/close",{method:"POST",headers:{"X-Jarvis-Token":window.JARVIS_TOKEN,"Content-Type":"application/json"},body:JSON.stringify({epoch}),keepalive:true}).catch(()=>{});});
poll();
