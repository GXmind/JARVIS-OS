import {$} from "../core/dom.js";
export function createWeatherController(api,getNavigation){
let weatherTimer=null;
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
return {refresh:updateWeather,stop:()=>clearTimeout(weatherTimer)};
}
