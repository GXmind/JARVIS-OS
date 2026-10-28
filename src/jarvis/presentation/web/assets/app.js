import {$} from "./core/dom.js";
import {state,metrics} from "./core/state.js";
import {createClient} from "./core/client.js";
import {createHUD} from "./ui/hud.js";
import {createWeatherController} from "./ui/weather.js";
import {createSettings} from "./ui/settings.js";

let navigation=null,navigationPromise=null,lastNavigationId=0;
const canvas=$("space");
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
  const data=await api("state");Object.assign(state,data);pollErrors=0;
  const labels={idle:state.phase==="initial"?"静候指令":"与你同在",listening:"正在聆听",thinking:"正在思考",speaking:"正在回应"};
  $("phaseLabel").textContent=state.mapReady?(state.mapTrip||"三维粒子城市 · 出行规划"):
   state.mapOpen?(state.mapStatus||"正在准备导航…"):(labels[state.activity]||"静候指令");
  if(state.mapOpen&&!state.mapReady){
   $("subtitle").textContent=state.mapStatus||"正在准备导航…";
   $("subtitle").classList.toggle("visible",$("command").hidden);
   $("subtitle").classList.toggle("error",state.mapStage==="error");
  }else if(state.presenting||Date.now()>localSubtitleUntil){
   $("subtitle").textContent=state.subtitle.slice(0,460);
   $("subtitle").classList.toggle("visible",!!state.subtitle&&$("command").hidden);
  }
  revision=data.revision;
  updateHUD();
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
function closeCommand(){$("command").hidden=true;$("thought").blur();}
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
 try{await api("send",{text});$("thought").value="";closeCommand();}
 catch(error){message(error.message,true);}
};
addEventListener("keydown",async event=>{
 if(event.key==="Escape"){
  event.preventDefault();
  if(!$("settingsLayer").hidden){$("settingsLayer").hidden=true;return;}
  if(!$("command").hidden){closeCommand();return;}
  if(navigation?.isOpen){navigation.close();return;}
  $("exitLayer").hidden?openExit():closeExit();return;
 }
 if(!$("exitLayer").hidden){
  if(event.key==="ArrowLeft"||event.key==="ArrowRight"){event.preventDefault();selectExit(exitSelection+1);}
  if(event.key==="Enter"){event.preventDefault();(exitSelection?$("quit"):$("continue")).click();}
  return;
 }
 if(!$("settingsLayer").hidden)return;
 if(event.key==="F2"){event.preventDefault();openSettings();return;}
 if(event.key==="F3"){
  event.preventDefault();getNavigation().then(map=>map.isOpen?map.close():map.open()).catch(error=>message(error.message,true));return;
 }
 if(event.key==="F6"){event.preventDefault();frameBudget=frameBudget<45?1000/20:1000/30;if(visual)visual.setLowQuality(frameBudget>45);message(frameBudget<45?"流畅特效":"节能特效",false,2);return;}
 if(event.key==="F8"&&!event.repeat){
  event.preventDefault();try{await api("record",{});}catch(error){message(error.message,true);}return;
 }
 if(event.key==="Enter"&&$("command").hidden){
  event.preventDefault();$("subtitle").classList.remove("visible");$("command").hidden=false;$("thought").focus();
 }
});
$("dragZone").onpointerdown=event=>{if(event.button===0)api("drag",{}).catch(()=>{});};
canvas.onpointerdown=event=>{
 if(state.mapReady)return;
 if(Math.hypot(event.clientX-CX,event.clientY-CY)<R*.95)api("record",{}).catch(error=>message(error.message,true));
};
window.__sceneMetrics=metrics;
import("./features/map/controls.js").then(({bindMapControls})=>{
 bindMapControls(canvas,state,{onViewEnd:()=>navigation?.commitView(),onZoom:()=>navigation?.scheduleViewCommit()});
}).catch(error=>message("地图手势加载失败："+error.message,true));
