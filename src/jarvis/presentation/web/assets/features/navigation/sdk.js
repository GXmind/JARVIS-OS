/* AMap SDK loading and provider error translation. */
export function providerError(status,result){
 const info=typeof result==="string"?result:String(result?.info||"");
 const codes={INVALID_USER_KEY:"高德 Key 无效",INVALID_USER_SCODE:"高德安全密钥校验失败",
  USERKEY_PLAT_NOMATCH:"高德 Key 平台类型不匹配",OVER_QUOTA:"高德调用配额不足",
  SERVICE_NOT_AVAILABLE:"高德服务暂不可用"};
 for(const [code,label] of Object.entries(codes))if(info.includes(code))return label;
 return status==="no_data"?"未找到地点或可用路线，请核对起点、终点名称":"高德出行查询失败，请检查权限与网络";
}
let sdkPromise=null;
export async function loadAMap(config){
 if(!config.configured)throw new Error(config.message||"请先在 F2 配置高德凭证。");
 if(!sdkPromise){
  sdkPromise=new Promise((resolve,reject)=>{
   if(window.AMap?.Driving){resolve(window.AMap);return;}
   window._AMapSecurityConfig={serviceHost:location.origin+"/_AMapService"};
   const script=document.createElement("script");script.nonce=window.JARVIS_TOKEN;script.async=true;
   script.src="https://webapi.amap.com/maps?"+new URLSearchParams({v:"2.0",key:config.key});
   const timer=setTimeout(()=>{script.remove();reject(new Error("高德数据组件加载超时。"));},25000);
   script.onload=()=>{clearTimeout(timer);window.AMap?resolve(window.AMap):reject(new Error("高德组件未初始化。"));};
   script.onerror=()=>{clearTimeout(timer);reject(new Error("高德组件无法下载。"));};
   document.head.append(script);
  }).catch(error=>{sdkPromise=null;throw error;});
 }
 const A=await sdkPromise;
 await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error("高德出行插件加载超时。")),18000);
  A.plugin(["AMap.Driving","AMap.Walking","AMap.Transfer","AMap.Geocoder","AMap.Weather","AMap.PlaceSearch"],()=>{clearTimeout(timer);resolve();});
 });
 return A;
}
