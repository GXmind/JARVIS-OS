import {$} from "../core/dom.js";
export function createHUD(state,metrics){
let lastHudSecond=-1,waveTime=0;
const cpuHistory=Array(36).fill(null);
const formatClock=new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",hour:"2-digit",minute:"2-digit",hour12:false});
const formatDate=new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",weekday:"short"});
function updateHUD(){
 const activity=state.activity,wake=state.wake||{},wakeReady=wake.state==="waiting";
 const counts=state.counts||{},modules=state.modules||{},system=state.telemetry||{};
 $("cloudLabel").textContent=state.mock?"SIMULATION":"CLOUD CONNECTED";
 $("micStatus").textContent=state.capturing?"正在录音 · PC INPUT":wakeReady?"唤醒待机 · hi jarvis":wake.state==="loading"?"唤醒组件准备中":"电脑麦克风 · 待机";
 $("modelStatus").textContent=state.mock?"模拟模式 · 无云端调用":modules.model||"云端 API";
 $("ttsStatus").textContent=modules.tts==="windows"?"Windows 系统语音":modules.tts==="api"?"云端语音合成":"播报已关闭";
 $("memoryCount").textContent=counts.memories??0;$("memoryCountText").textContent=(counts.memories??0)+" 条";
 $("messageCount").textContent=counts.messages??0;
 $("memoryMeter").style.width=(counts.memories?Math.min(95,8+Math.log2(counts.memories+1)*12):0)+"%";
 $("voiceTrigger").classList.toggle("recording",!!state.capturing);
 $("voiceDockLeft").textContent=state.capturing?"LISTENING":wakeReady?"HI JARVIS":"PC MICROPHONE";
 const captions={idle:state.phase==="initial"?"等待您的下一句指令":"与你同在",listening:"正在聆听",transcribing:"正在辨识语音",modeling:"正在编织粒子造型",thinking:"正在整理思绪",speaking:"正在回应您"};
 $("coreCaption").textContent=(state.mapReady&&!state.mapDetached)?(state.mapSummary||"高德地图 · 路线预览"):
  (state.mapOpen&&!state.mapDetached)?(state.mapStatus||"正在准备导航…"):(state.center?.active?state.center.plan.title+" · 拖动旋转 / 滚轮缩放":captions[activity]||"等待指令");
 $("coreMode").textContent=(state.mapReady&&!state.mapDetached)?"PARTICLE CITY / 三维导航":(state.mapOpen&&!state.mapDetached)?
  (state.mapStage==="await_choice"?"WAITING / 请确认地点":state.mapStage==="error"?"NAVIGATION / 规划未完成":"NAVIGATION / 正在规划"):
  state.center?.active?"PARTICLE CONCEPT / 粒子造型":state.phase==="initial"?"INITIAL / 待机形态":"DIALOGUE / 对话形态";
 $("audioLabel").textContent=state.capturing?"MIC INPUT":activity==="speaking"?(modules.auto_speak&&modules.tts!=="off"?"VOICE OUTPUT":"TEXT OUTPUT"):activity==="transcribing"?"ASR PROCESSING":"STANDBY";
 $("audioSource").textContent=state.capturing?"实际输入音量":activity==="speaking"?(modules.auto_speak&&modules.tts!=="off"?"实际输出音量":"文本回应"):wakeReady?"本机唤醒监听":"麦克风未启用";
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
return updateHUD;
}
