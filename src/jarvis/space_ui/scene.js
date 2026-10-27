"use strict";
const $=id=>document.getElementById(id);
const canvas=$("space"),TOKEN=window.JARVIS_TOKEN;
const state={phase:"initial",activity:"idle",level:0,subtitle:"",busy:false,telemetry:{},counts:{},modules:{}};
const metrics=window.__sceneMetrics={frames:0,meanMs:0,particles:0,phase:"initial",ready:false};
let W=innerWidth,H=innerHeight,CX=W/2,CY=H/2,R=H*.29;
let frameBudget=1000/30,exitSelection=0,hintTimer=null,localSubtitleUntil=0,revision=-1,pollErrors=0;
let visual=null,lastHudSecond=-1,waveTime=0,weatherTimer=null;
const cpuHistory=Array(36).fill(null);
let navigation=null,navigationPromise=null,lastNavigationId=0;
async function getNavigation(){
 if(navigation)return navigation;
 if(!navigationPromise)navigationPromise=import("/navigation.js").then(module=>{
  navigation=new module.NavigationController({api,state,message,openSettings});
  window.__navigation=navigation;return navigation;
 }).catch(error=>{navigationPromise=null;throw error;});
 return navigationPromise;
}


addEventListener("resize",()=>{W=innerWidth;H=innerHeight;CX=W/2;CY=H/2;R=H*.29;});
import("/visual.js").then(module=>{visual=module.createVisual(canvas,state,metrics);})
.catch(error=>{window.__renderError=String(error.stack||error);message("WebGL 启动失败，请检查图形驱动和浏览器图形加速。",true,30);});
const formatClock=new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",hour:"2-digit",minute:"2-digit",hour12:false});
const formatDate=new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",weekday:"short"});
function updateHUD(){
 const activity=state.activity;
 const counts=state.counts||{},modules=state.modules||{},system=state.telemetry||{};
 $("cloudLabel").textContent=state.mock?"SIMULATION":"CLOUD CONNECTED";
 $("micStatus").textContent=state.capturing?"正在录音 · PC INPUT":"电脑麦克风 · 待机";
 $("modelStatus").textContent=state.mock?"模拟模式 · 无云端调用":modules.model||"云端 API";
 $("ttsStatus").textContent=modules.tts==="windows"?"Windows 系统语音":modules.tts==="api"?"云端语音合成":"播报已关闭";
 $("memoryCount").textContent=counts.memories??0;$("memoryCountText").textContent=(counts.memories??0)+" 条";
 $("messageCount").textContent=counts.messages??0;
 $("memoryMeter").style.width=(counts.memories?Math.min(95,8+Math.log2(counts.memories+1)*12):0)+"%";
 $("voiceTrigger").classList.toggle("recording",!!state.capturing);
 $("voiceDockLeft").textContent=state.capturing?"LISTENING":"PC MICROPHONE";
 const captions={idle:state.phase==="initial"?"等待您的下一句指令":"与你同在",listening:"正在聆听",thinking:"正在整理思绪",speaking:"正在回应您"};
 $("coreCaption").textContent=state.mapReady?(state.mapSummary||"高德地图 · 路线预览"):
  state.mapOpen?(state.mapStatus||"正在准备导航…"):(captions[activity]||"等待指令");
 $("coreMode").textContent=state.mapReady?"PARTICLE CITY / 三维导航":state.mapOpen?
  (state.mapStage==="await_choice"?"WAITING / 请确认地点":state.mapStage==="error"?"NAVIGATION / 规划未完成":"NAVIGATION / 正在规划"):
  state.phase==="initial"?"INITIAL / 待机形态":"DIALOGUE / 对话形态";
 $("audioLabel").textContent=state.capturing?"MIC INPUT":activity==="speaking"?"VOICE OUTPUT":"STANDBY";
 $("audioSource").textContent=state.capturing?"实际输入音量":activity==="speaking"?"实际输出音量":"麦克风未启用";
 $("volumeLabel").textContent=Math.round((state.level||0)*100)+"%";
 waveTime+=.19;
 const amp=(state.level||0)*22;
 const makeWave=(offset,scale)=>Array.from({length:74},(_,i)=>{
  const x=i/73*220,env=Math.sin(i/73*Math.PI);
  const y=34+Math.sin(i*.27+waveTime+offset)*amp*scale*env+Math.sin(i*.09-waveTime*1.3)*amp*.27*env;
  return (i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1);
 }).join(" ");
 const wave=makeWave(0,1);$("wave1").setAttribute("d",wave);
 $("wave2").setAttribute("d",makeWave(1.8,.65));$("wave3").setAttribute("d",makeWave(3.3,.8));
 $("waveArea").setAttribute("d",wave+" L220 64 L0 64Z");
 if(system.cpu!=null){$("cpuText").textContent=Math.round(system.cpu)+"%";$("cpuMeter").style.width=system.cpu+"%";}
 if(system.memory!=null){$("ramText").textContent=system.memory+"%";$("ramMeter").style.width=system.memory+"%";}
 if(system.memory_used_gb!=null)$("ramDetail").textContent=system.memory_used_gb+" / "+system.memory_total_gb+" GB";
 const seconds=system.uptime||0;
 $("uptime").textContent=[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,"0")).join(":");
 $("renderMode").textContent=metrics.ready?"WEBGL2 / "+(metrics.fps||"—")+" FPS":"GRAPHICS STARTING";
 const now=new Date(),second=Math.floor(now.getTime()/1000);
 if(second!==lastHudSecond){
  $("localTime").textContent=formatClock.format(now);$("localDate").textContent=formatDate.format(now).replaceAll("/"," · ");
  lastHudSecond=second;
  cpuHistory.shift();cpuHistory.push(system.cpu??null);
  const trace=cpuHistory.map((v,i)=>(i?"L":"M")+(i/35*220).toFixed(1)+" "+(44-(v??0)*.36).toFixed(1)).join(" ");
  $("loadTrace").setAttribute("d",trace);
 }
}
async function updateWeather(){
 clearTimeout(weatherTimer);
 try{
  let data=await api("weather");
  try{
   const nav=await getNavigation(),live=await nav.weather();
   if(live){await api("weather/live",live);data=await api("weather");}
  }catch(_error){}
  $("weatherCity").textContent=data.city||"虎丘区";
  $("weatherSource").textContent=data.source||"区域预报";
  $("forecastSource").hidden=!(data.forecast?.length&&(data.source||"").includes("高德"));
  $("forecast").title=data.forecast_source||"Open-Meteo 区域预报";
  $("weatherSource").href=(data.source||"").includes("高德")?"https://www.amap.com/":"https://open-meteo.com/";
  if(typeof data.temperature==="number"){
   $("temperature").replaceChildren(document.createTextNode(String(Math.round(data.temperature))));
   const unit=document.createElement("sup");unit.textContent="°C";$("temperature").append(unit);
   $("weatherDescription").textContent=data.label||"";
   $("feelsLike").textContent="体感 "+(data.feels_like==null?"--":Math.round(data.feels_like))+"°";
   $("humidity").textContent=data.humidity==null?"--%":data.humidity+"%";
   $("wind").textContent=data.wind==null?(data.wind_power?data.wind_power+" 级":"-- m/s"):Number(data.wind).toFixed(1)+" m/s";
   const forecast=$("forecast");forecast.replaceChildren();
   for(const item of data.forecast||[]){
    const row=document.createElement("div");
    const date=document.createElement("span");date.textContent=item.date.slice(5).replace("-"," / ");
    const range=document.createElement("strong");range.textContent=Math.round(item.high)+"° / "+Math.round(item.low)+"°";
    const label=document.createElement("small");label.textContent=item.label;
    row.append(date,range,label);forecast.append(row);
   }
   const observed=(data.observation||"").slice(11,16);
   $("weatherUpdate").textContent=(data.status==="stale"?"离线缓存 · ":data.status==="cached"?"缓存 · ":"更新 ")+observed;
  }else{
   $("weatherDescription").textContent=data.status==="offline"?"天气暂时离线":"正在获取天气";
   $("weatherUpdate").textContent="等待有效数据";
  }
  weatherTimer=setTimeout(updateWeather,["loading","cached","offline"].includes(data.status)?10000:300000);
 }catch(_error){$("weatherUpdate").textContent="天气连接中断";weatherTimer=setTimeout(updateWeather,30000);}
}
updateWeather();
$("voiceTrigger").onclick=()=>api("record",{}).catch(error=>message(error.message,true));
$("microphoneModule").onclick=$("voiceTrigger").onclick;
async function api(path,body){
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),path==="city/context"?45000:15000);
 try{
  const response=await fetch("/api/"+path,{method:body===undefined?"GET":"POST",signal:controller.signal,
   headers:{"X-Jarvis-Token":TOKEN,...(body===undefined?{}:{"Content-Type":"application/json"})},
   ...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||"本机服务暂不可用");
  return data;
 }catch(error){
  if(error.name==="AbortError")throw new Error(path==="city/context"?"城市数据加载超时":"本机请求超时，请重试");
  throw error;
 }finally{clearTimeout(timer);}
}
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
const fieldLabels={
 API_BASE_URL:"对话 / 云端播报 API 地址",API_MODEL:"对话模型",API_KEY:"对话 / 云端播报密钥",CHAT_MODE:"对话模式",
 ASR_MODE:"语音识别",ASR_BASE_URL:"语音识别 API 地址（独立服务）",ASR_API_KEY:"语音识别密钥（独立服务）",ASR_MODEL:"语音识别模型（录音转文字）",TTS_MODE:"语音播报",TTS_MODEL:"播报模型",TTS_VOICE:"音色",
 INPUT_DEVICE:"输入设备编号（空为系统默认）",OUTPUT_DEVICE:"输出设备编号（空为系统默认）",
 SAMPLE_RATE:"录音采样率",MAX_RECORD_SECONDS:"最长录音秒数",REQUEST_TIMEOUT:"请求超时秒数",AUTO_SPEAK:"自动播报",WEATHER_CITY:"天气城市 / 区县",WEATHER_ADCODE:"天气行政区编码（虎丘区 320505）",
 AMAP_JS_KEY:"高德 Web端（JS API）Key",AMAP_SECURITY_JSCODE:"高德安全密钥（securityJsCode）",AMAP_CITY:"地图默认城市",AMAP_DEFAULT_ORIGIN:"常用出发地（请填写具体地址或地点）"};
const options={CHAT_MODE:[["mock","模拟"],["api","云端 API"]],ASR_MODE:[["off","关闭"],["api","云端 API"]],
 TTS_MODE:[["windows","Windows 系统"],["api","云端 API"],["off","关闭"]],AUTO_SPEAK:[["false","关闭"],["true","开启"]]};
async function openSettings(){
 closeCommand();closeExit();
 try{
  const config=await api("config");const fields=$("fields");fields.replaceChildren();
  for(const [key,label]of Object.entries(fieldLabels)){
   const box=document.createElement("div");box.className="field";
   const caption=document.createElement("label");caption.textContent=label;caption.htmlFor="cfg-"+key;
   const input=document.createElement(options[key]?"select":"input");input.id="cfg-"+key;input.name=key;
   if(options[key])for(const [value,text]of options[key]){
    const option=document.createElement("option");option.value=value;option.textContent=text;input.append(option);
   }
   if(["API_KEY","ASR_API_KEY","AMAP_JS_KEY","AMAP_SECURITY_JSCODE"].includes(key)){
    input.type="password";input.autocomplete="new-password";
    const present=key==="API_KEY"?config.KEY_PRESENT:config[key+"_PRESENT"];
    input.placeholder=present?"已保存 · 留空保留":"尚未配置";
   }
   input.value=config[key]||"";
   if(key==="ASR_BASE_URL")input.placeholder="填写支持音频转写的服务地址；留空沿用上方地址";
   if(key==="ASR_MODEL")input.placeholder="服务商提供的转写模型，不能填 DeepSeek 对话模型";
   box.append(caption,input);fields.append(box);
  }
  $("configNote").textContent="语音链路：录音 → 语音识别 → 对话模型 → 播报。DeepSeek 可用于对话；识别需支持音频转写的服务。独立识别地址须配套填写独立密钥；密钥留空保留。";
  $("settingsLayer").hidden=false;
  try{
   const list=await api("devices");
   $("deviceList").textContent=list.map(d=>d.index+" · "+d.name+" ["+(d.inputs?"输入":"输出")+"]").join("   /   ");
  }catch(_error){$("deviceList").textContent="暂时无法获取音频设备。";}
 }catch(error){message(error.message,true);}
}
$("closeSettings").onclick=()=>{$("settingsLayer").hidden=true;};
$("settingsForm").onsubmit=async event=>{
 event.preventDefault();
 try{
  const values=Object.fromEntries(new FormData($("settingsForm")));
  await api("config",values);$("settingsLayer").hidden=true;message("设置已保存。");updateWeather();
  if(navigation)navigation.config=null;
  if(values.AMAP_JS_KEY||values.AMAP_SECURITY_JSCODE){
   message("地图凭证已保存，正在刷新地图运行环境。");
   setTimeout(()=>location.reload(),400);
  }
 }catch(error){$("configNote").textContent=error.message;}
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
let cityDrag=null;
canvas.addEventListener("pointerdown",event=>{
 if(!state.mapReady)return;
 cityDrag={x:event.clientX,yaw:state.cityYaw||0};canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener("pointermove",event=>{if(cityDrag)state.cityYaw=cityDrag.yaw+(event.clientX-cityDrag.x)*.005;});
canvas.addEventListener("pointerup",()=>{cityDrag=null;});
canvas.addEventListener("pointercancel",()=>{cityDrag=null;});
canvas.addEventListener("wheel",event=>{
 if(state.mapReady){event.preventDefault();state.cityZoom=Math.max(.6,Math.min(2.2,(state.cityZoom||1)*Math.exp(-event.deltaY*.001)));}
},{passive:false});
