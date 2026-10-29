import {bindCenterControls} from "./features/center.js";
import {HandCamera} from "./features/hand/camera.js";
import {MapWorkspaceClient} from "./features/map/workspace.js";
import {$} from "./core/dom.js";
import {state,metrics} from "./core/state.js";
import {createClient} from "./core/client.js";
import {createHUD} from "./ui/hud.js";
import {createWeatherController} from "./ui/weather.js";
import {createSettings} from "./ui/settings.js";

let visualPrompt=false,centerReport="";
let navigation=null,navigationPromise=null,lastNavigationId=0;
const canvas=$("space");bindCenterControls(canvas,state);
const api=createClient(window.JARVIS_TOKEN);
const updateHUD=createHUD(state,metrics);
const weather=createWeatherController(api,getNavigation);
const updateWeather=()=>weather.refresh();
const {openSettings}=createSettings({api,message,closeCommand,closeExit,updateWeather,onSaved:()=>{if(navigation)navigation.config=null;}});
let W=innerWidth,H=innerHeight,CX=W/2,CY=H/2,R=H*.29;
let frameBudget=1000/30,exitSelection=0,hintTimer=null,localSubtitleUntil=0,revision=-1,pollErrors=0;
let visual=null;

async function getNavigation(){
 if(navigation)return navigation;
 if(!navigationPromise)navigationPromise=import("./features/navigation/controller.js").then(module=>{
  navigation=new module.NavigationController({api,state,message,openSettings});
  window.__navigation=navigation;return navigation;
 }).catch(error=>{navigationPromise=null;throw error;});
 return navigationPromise;
}


addEventListener("resize",()=>{W=innerWidth;H=innerHeight;CX=W/2;CY=H/2;R=H*.29;});
import("./rendering/energy.js").then(module=>{visual=module.createVisual(canvas,state,metrics);})
.catch(error=>{window.__renderError=String(error.stack||error);message("WebGL 启动失败，请检查图形驱动和浏览器图形加速。",true,30);});
updateWeather();
$("voiceTrigger").onclick=()=>api("record",{}).catch(error=>message(error.message,true));
$("microphoneModule").onclick=$("voiceTrigger").onclick;
function message(text,error=false,seconds=7){
 $("subtitle").textContent=text;$("subtitle").classList.add("visible");
 localSubtitleUntil=Date.now()+seconds*1000;
 $("subtitle").classList.toggle("error",error);
}
async function poll(){
 try{
  const data=await api("state?center_id="+(state.center?.id??-1));if(data.center?.same)data.center.plan=state.center?.plan;if(data.center?.active&&data.center?.plan?.title!==state.center?.plan?.title){state.centerYaw=0;delete state.centerPitch;state.centerZoom=1;}Object.assign(state,data);pollErrors=0;
  const labels={idle:state.phase==="initial"?"静候指令":"与你同在",listening:"正在聆听",transcribing:"正在辨识语音",modeling:"正在编织粒子造型",thinking:"正在思考",speaking:"正在回应"};
  $("phaseLabel").textContent=(state.mapReady&&!state.mapDetached)?(state.mapTrip||"三维粒子城市 · 出行规划"):
   (state.mapOpen&&!state.mapDetached)?(state.mapStatus||"正在准备导航…"):(state.center?.active?state.center.plan.title:labels[state.activity]||"静候指令");
  if(state.mapOpen&&!state.mapReady&&!state.mapDetached){
   $("subtitle").textContent=state.mapStatus||"正在准备导航…";
   $("subtitle").classList.toggle("visible",$("command").hidden);
   $("subtitle").classList.toggle("error",state.mapStage==="error");
  }else if(state.presenting||Date.now()>localSubtitleUntil){
   $("subtitle").textContent=state.subtitle.slice(0,460);
   $("subtitle").classList.toggle("visible",!!state.subtitle&&$("command").hidden);
  }
  if(data.center?.active&&metrics.centerBuild===data.center.build){
   const report=data.center.build+":"+(metrics.centerError?"error":!metrics.centerLoading&&metrics.centerMorph===1?"ready":"loading");
   if(!report.endsWith("loading")&&centerReport!==report){centerReport=report;api("center/result",{build:data.center.build,ok:!metrics.centerError}).catch(()=>{});if(metrics.centerError)message("粒子绘制失败："+metrics.centerError,true,14);}
  }
  revision=data.revision;
  updateHUD();
  const wake=data.wake||{};$("wakeToggle").textContent=wake.state==="waiting"?"hi jarvis · 唤醒待机":wake.state==="loading"?"唤醒准备中":wake.state==="error"?"唤醒未就绪":wake.state==="paused"?"唤醒暂歇":"F10 · 开启唤醒";
  $("wakeToggle").title=wake.message||"F10 开关本机唤醒；唤醒后说出指令，说完自动结束。";
  if(data.navigation?.id>lastNavigationId){
   lastNavigationId=data.navigation.id;
   getNavigation().then(map=>map.handle(data.navigation)).catch(error=>message(error.message,true));
  }
 }catch(error){if(++pollErrors===4)message("本机服务连接已中断。",true);}
 setTimeout(poll,180);
}
poll();
function hints(){clearTimeout(hintTimer);$("hints").classList.add("visible");hintTimer=setTimeout(()=>$("hints").classList.remove("visible"),6000);}
hints();addEventListener("pointermove",hints,{passive:true});
function closeCommand(){$("command").hidden=true;$("thought").blur();visualPrompt=false;}
function selectExit(n){
 exitSelection=(n+2)%2;
 $("continue").classList.toggle("selected",exitSelection===0);
 $("quit").classList.toggle("selected",exitSelection===1);
}
function openExit(){closeCommand();$("settingsLayer").hidden=true;$("exitLayer").hidden=false;selectExit(0);}
function closeExit(){$("exitLayer").hidden=true;}
$("continue").onclick=closeExit;
$("quit").onclick=async()=>{try{await api("close",{});}catch(_error){}};
$("continue").onpointerenter=()=>selectExit(0);
$("quit").onpointerenter=()=>selectExit(1);
$("command").onsubmit=async event=>{
 event.preventDefault();const text=$("thought").value.trim();if(!text)return;
 try{await api("send",{text,visual:visualPrompt});$("thought").value="";closeCommand();}
 catch(error){message(error.message,true);}
};
addEventListener("keydown",async event=>{
 if(event.key==="Escape"){
  event.preventDefault();
  if(!$("settingsLayer").hidden){$("settingsLayer").hidden=true;return;}
  if(!$("command").hidden){closeCommand();return;}
  if(navigation?.isOpen){navigation.close();return;}
  if(state.center?.active||state.center?.pending){await api("center/close",{});return;}
  $("exitLayer").hidden?openExit():closeExit();return;
 }
 if(!$("exitLayer").hidden){
  if(event.key==="ArrowLeft"||event.key==="ArrowRight"){event.preventDefault();selectExit(exitSelection+1);}
  if(event.key==="Enter"){event.preventDefault();(exitSelection?$("quit"):$("continue")).click();}
  return;
 }
 if(!$("settingsLayer").hidden)return;
 if(event.key==="F10"&&!event.repeat){event.preventDefault();$("wakeToggle").click();return;}
 if(event.key==="F9"&&!event.repeat){event.preventDefault();document.getElementById("cameraToggle").click();return;}
 if(event.key==="F2"){event.preventDefault();openSettings();return;}
 if(event.key==="F3"){
  event.preventDefault();getNavigation().then(map=>map.isOpen?map.close():map.open()).catch(error=>message(error.message,true));return;
 }
 if(event.key==="F6"){event.preventDefault();frameBudget=frameBudget<45?1000/20:1000/30;if(visual)visual.setLowQuality(frameBudget>45);message(frameBudget<45?"流畅特效":"节能特效",false,2);return;}
 if(event.key==="F8"&&!event.repeat){
  event.preventDefault();try{await api("record",{});}catch(error){message(error.message,true);}return;
 }
 if(event.key==="F4"&&!event.altKey&&!event.ctrlKey&&!event.metaKey){event.preventDefault();visualPrompt=true;document.querySelector("#command label").textContent="自由绘制 · 描述主体、色彩、构图和动作";$("thought").placeholder="例如：星河中的鲸鱼，尾巴缓慢摆动，周围有三颗金色星星";$("command").hidden=false;$("thought").focus();return;}
 if(event.key==="Enter"&&$("command").hidden){visualPrompt=false;document.querySelector("#command label").textContent="告诉 JARVIS";
  event.preventDefault();$("subtitle").classList.remove("visible");$("command").hidden=false;$("thought").focus();
 }
});
$("dragZone").onpointerdown=event=>{if(event.button===0)api("drag",{}).catch(()=>{});};
canvas.onpointerdown=event=>{
 if(state.mapReady&&!state.mapDetached||state.center?.active)return;
 if(Math.hypot(event.clientX-CX,event.clientY-CY)<R*.95)api("record",{}).catch(error=>message(error.message,true));
};
window.__sceneMetrics=metrics;
import("./features/map/controls.js").then(({bindMapControls})=>{
 bindMapControls(canvas,state,{onViewEnd:()=>navigation?.commitView(),onZoom:()=>navigation?.scheduleViewCommit()});
}).catch(error=>message("地图手势加载失败："+error.message,true));

const workspace=window.__mapWorkspace=new MapWorkspaceClient({api,state,getNavigation,message});
const camera=window.__handCamera=new HandCamera({api,onAction:action=>workspace.gesture(action).catch(error=>message(error.message,true)),
 video:$("handVideo"),overlay:$("handOverlay"),onStatus:(text,error=false)=>{
  $("handStatus").textContent=text;$("cameraToggle").textContent=camera.active?"F9 · 关闭手势":"F9 · 启用手势";
  $("handPanel").hidden=!camera.active;if(error)message(text,true,14);
 }});
$("cameraToggle").onclick=()=>{if(camera.active){camera.stop();$("handPanel").hidden=true;$("cameraToggle").textContent="F9 · 启用手势";}else{ $("handPanel").hidden=false;void camera.start();}};
$("handHide").onclick=()=>{const collapsed=document.querySelector(".hand-preview").classList.toggle("collapsed");$("handHide").textContent=collapsed?"显示预览":"隐藏预览";};
$("mapDetach").onclick=()=>workspace.detach();$("mapReturn").onclick=()=>workspace.closeRemote();
api("displays").then(displays=>{for(const display of displays){const option=document.createElement("option");option.value=display.id;option.textContent="屏幕 "+(display.id+1)+(display.primary?" · 主屏":"");$("mapDisplay").append(option);}}).catch(()=>{});
addEventListener("pagehide",()=>{camera.stop();workspace.stop();visual?.stop();});

$("wakeToggle").onclick=async()=>{try{const config=await api("config");await api("wake",{enabled:config.WAKE_ENABLED!=="true"});}catch(error){message(error.message,true);}};
