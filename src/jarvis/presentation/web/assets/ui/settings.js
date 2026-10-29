import {$} from "../core/dom.js";
export function createSettings({api,message,closeCommand,closeExit,updateWeather,onSaved}){
const fieldLabels={
 VISUAL_RESPONSE_MODE:"绘制思考强度（DeepSeek 官方接口）",RESPONSE_MODE:"回应速度（DeepSeek 官方接口）",CHAT_STREAM:"流式回复（降低首句等待）",WAKE_ENABLED:"本机 hi jarvis 唤醒",WAKE_TIMEOUT_SECONDS:"唤醒后等待指令秒数",WAKE_SILENCE_SECONDS:"说完后静音结束秒数",
 API_BASE_URL:"对话 / 云端播报 API 地址",API_MODEL:"对话模型",API_KEY:"对话 / 云端播报密钥",CHAT_MODE:"对话模式",
 ASR_MODE:"语音识别",ASR_BASE_URL:"语音识别 API 地址（独立服务）",ASR_API_KEY:"语音识别密钥（独立服务）",ASR_MODEL:"语音识别模型（录音转文字）",TTS_MODE:"语音播报",TTS_MODEL:"播报模型",TTS_VOICE:"音色",
 INPUT_DEVICE:"输入设备编号（空为系统默认）",OUTPUT_DEVICE:"输出设备编号（空为系统默认）",
 SAMPLE_RATE:"录音采样率",MAX_RECORD_SECONDS:"最长录音秒数",REQUEST_TIMEOUT:"请求超时秒数",AUTO_SPEAK:"自动播报",WEATHER_CITY:"天气城市 / 区县",WEATHER_ADCODE:"天气行政区编码（虎丘区 320505）",
 MAP_VIEW_METERS:"地图街区范围（600–5000 米，下次导航生效）",MAP_HEIGHT_SCALE:"楼高视觉倍率（1–32，下次导航生效）",
 AMAP_JS_KEY:"高德 Web端（JS API）Key",AMAP_SECURITY_JSCODE:"高德安全密钥（securityJsCode）",AMAP_CITY:"地图默认城市",AMAP_DEFAULT_ORIGIN:"常用出发地（请填写具体地址或地点）"};
const options={VISUAL_RESPONSE_MODE:[["balanced","平衡细节与速度"],["fast","优先速度"],["deep","优先深入设计"],["provider","服务商默认"]],RESPONSE_MODE:[["fast","快速回应"],["balanced","轻量思考"],["deep","深入思考"],["provider","服务商默认"]],CHAT_STREAM:[["true","开启"],["false","关闭"]],WAKE_ENABLED:[["true","开启"],["false","关闭"]],CHAT_MODE:[["mock","模拟"],["api","云端 API"]],ASR_MODE:[["off","关闭"],["api","云端 API"]],
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
  onSaved();
  if(values.AMAP_JS_KEY||values.AMAP_SECURITY_JSCODE){
   message("地图凭证已保存，正在刷新地图运行环境。");
   setTimeout(()=>location.reload(),400);
  }
 }catch(error){$("configNote").textContent=error.message;}
};
return {openSettings};
}
