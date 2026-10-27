import {resetMapView,DEFAULT_EXTENT,DEFAULT_HEIGHT_SCALE} from "./map_controls.js";
import {rankPlaces,confidentPlace,groundDistance} from "./places.js";
/* Real AMap JS API integration. No fabricated basemap or fallback routes. */
export function coordinates(value){
 if(typeof value==="string"){
  const parts=value.split(",");if(parts.length!==2||parts.some(item=>!item.trim()))return null;
  value=parts.map(Number);
 }
 let lng,lat;
 if(Array.isArray(value)){[lng,lat]=value;}
 else if(value){lng=typeof value.getLng==="function"?value.getLng():value.lng;lat=typeof value.getLat==="function"?value.getLat():value.lat;}
 if(lng==null||lat==null||lng===""||lat==="")return null;
 lng=Number(lng);lat=Number(lat);
 return Number.isFinite(lng)&&Number.isFinite(lat)&&Math.abs(lng)<=180&&Math.abs(lat)<=90?[lng,lat]:null;
}
export function extractRoute(route){
 const path=[],steps=[];
 for(const step of route.steps||[]){
  let raw=step.path||[];if(typeof raw==="string")raw=raw.split(";");
  for(const value of raw){
   const point=coordinates(value);if(!point)continue;
   const previous=path[path.length-1];
   if(!previous||Math.abs(previous[0]-point[0])+Math.abs(previous[1]-point[1])>1e-9)path.push(point);
  }
  if(step.instruction)steps.push({instruction:String(step.instruction),road:String(step.road||""),distance:Number(step.distance)||0});
 }
 if(path.length<2)throw new Error("高德返回的路线缺少有效坐标，无法显示路线粒子。");
 const distance=Number(route.distance),seconds=Number(route.time);
 return {path,steps,distance:Number.isFinite(distance)?distance:null,seconds:Number.isFinite(seconds)?seconds:null};
}
export function screenPath(points){
 const clean=[],cumulative=[0];
 for(const value of points){
  const p=[Number(value[0]),Number(value[1])];if(!p.every(Number.isFinite))continue;
  const previous=clean[clean.length-1];
  if(previous&&Math.hypot(p[0]-previous[0],p[1]-previous[1])<.05)continue;
  if(previous)cumulative.push(cumulative[cumulative.length-1]+Math.hypot(p[0]-previous[0],p[1]-previous[1]));
  clean.push(p);
 }
 return {points:clean,cumulative,length:cumulative[cumulative.length-1]||0};
}
export function pointAt(path,distance){
 if(path.points.length<2||!path.length)return null;
 distance=Math.max(0,Math.min(path.length,distance));
 let lo=1,hi=path.cumulative.length-1;
 while(lo<hi){const mid=(lo+hi)>>1;if(path.cumulative[mid]<distance)lo=mid+1;else hi=mid;}
 const start=path.points[lo-1],end=path.points[lo],span=path.cumulative[lo]-path.cumulative[lo-1];
 const t=span?(distance-path.cumulative[lo-1])/span:0;
 return [start[0]+(end[0]-start[0])*t,start[1]+(end[1]-start[1])*t];
}
export function routeParticles(path,spacing=2.2,limit=3000){
 if(!path.length||path.points.length<2)return [];
 const count=Math.min(limit,Math.max(2,Math.ceil(path.length/Math.max(.5,spacing))+1));
 return Array.from({length:count},(_,i)=>{
  const p=pointAt(path,i/(count-1)*path.length);
  return {x:p[0],y:p[1],phase:i*.61803398875%1,size:.55+(i*17%11)/16};
 });
}
export function extractTransit(plan){
 let raw=plan.path||[];
 if(!raw.length){
  raw=[];
  for(const segment of plan.segments||[]){
   const detail=segment.transit||segment.walking||{};
   if(detail.path?.length)raw.push(...detail.path);
   else if(detail.steps?.length)for(const step of detail.steps)raw.push(...(step.path||[]));
   else if(detail.lines?.[0]?.path)raw.push(...detail.lines[0].path);
  }
 }
 const route=extractRoute({distance:plan.distance,time:plan.time,steps:[{path:raw}]});
 route.steps=(plan.segments||[]).map(segment=>({instruction:segment.instruction||
  segment.transit?.lines?.[0]?.name||"步行换乘"}));
 return route;
}
function providerError(status,result){
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
export function resolveRouteCommand(command,config){
 const copy={...command};
 const explicit=String(copy.origin||"").trim();
 const saved=String(config.default_origin||"").trim();
 if(copy.destination&&(copy.action==="route"||copy.action==="await_origin")){
  const useSaved=copy.origin_source==="saved"||!explicit;
  copy.origin=useSaved?(saved||explicit):explicit;
  copy.origin_source=useSaved&&copy.origin?"saved":explicit?"explicit":"missing";
  if(copy.origin)copy.action="route";
 }
 return copy;
}
const timeText=seconds=>seconds==null?"时间待确认":Math.max(1,Math.ceil(seconds/60))+" 分钟";
const distanceText=value=>value==null?"距离待确认":value<1000?Math.round(value)+" 米":(value/1000).toFixed(1)+" 公里";
export class NavigationController{
 constructor({api,state,message,openSettings}){
  this.api=api;this.state=state;this.message=message;this.openSettings=openSettings;
  this.config=null;this.AMap=null;this.map=null;this.isOpen=false;this.requestVersion=0;
  this.path=[];this.options=[];this.dots=[];this.routeBusy=false;this.currentContext=null;
  this.stage=document.getElementById("mapStage");
  this.controls=document.getElementById("travelOptions");
  this.panel=document.getElementById("travelPanel");
  this.resolved=null;this.pendingPlaceReject=null;
  for(const button of document.querySelectorAll("[data-city-view]"))button.onclick=()=>this.setView(button.dataset.cityView);
  const height=document.getElementById("cityHeight");
  if(height)height.oninput=()=>{
   this.state.cityHeightScale=Number(height.value);
   document.getElementById("cityHeightValue").textContent="×"+height.value;
  };
  const reset=document.getElementById("cityReset");
  if(reset)reset.onclick=()=>resetMapView(this.state);
 }
 status(text,error=false){this.state.mapStatus=text;this.message(text,error,error?14:5);}
 progress(stage,text,error=false){
  this.state.mapStage=stage;this.state.mapStatus=text;
  document.getElementById("travelStatus").textContent=text;
  this.message(text,error,error?14:5);
 }
 async weather(){
  const config=await this.api("map/config");if(!config.configured)return null;
  const A=await loadAMap(config);
  const adcode=config.weather_adcode||"320505";
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error("区县天气查询超时")),12000);
   new A.Weather().getLive(adcode,(error,data)=>{
    clearTimeout(timer);
    if(error){reject(new Error("区县天气获取失败"));return;}
    resolve({...data,adcode});
   });
  });
 }
 async open(command={}){
  this.isOpen=true;this.state.mapOpen=true;this.panel.hidden=false;
  document.body.classList.add("map-open");
  this.progress("preparing","正在准备通行方案…");
  const version=++this.requestVersion;this.command=command;
  if(this.pendingPlaceReject){this.pendingPlaceReject(new Error("已切换请求"));this.pendingPlaceReject=null;}
  this.state.cityView="start";resetMapView(this.state);this.resolved=null;
  for(const button of document.querySelectorAll("[data-city-view]"))button.classList.toggle("selected",button.dataset.cityView==="start");
  document.getElementById("cityViewLabel").textContent="起点街区 · 三维城市";
  document.getElementById("resolvedOrigin").textContent="";
  document.getElementById("resolvedDestination").textContent="";
  this.state.mapReady=false;this.state.mapSummary="";this.options=[];this.controls.replaceChildren();
  document.body.classList.remove("map-active");
  try{
   this.config=await this.api("map/config");
   if(version!==this.requestVersion)return;
   command=resolveRouteCommand(command,this.config);this.command=command;
   this.state.cityExtent=Number(this.config.view_meters)||DEFAULT_EXTENT;
   this.state.cityHeightScale=Number(this.config.height_scale)||DEFAULT_HEIGHT_SCALE;
   const height=document.getElementById("cityHeight");
   if(height)height.value=String(this.state.cityHeightScale);
   const value=document.getElementById("cityHeightValue");if(value)value.textContent="×"+this.state.cityHeightScale;
   document.getElementById("travelOriginSource").textContent=command.origin_source==="saved"?"起点 · F2 常用地址":"起点 · 本次指定";
   document.getElementById("travelOrigin").textContent=command.origin||this.config.default_origin||"尚未填写";
   document.getElementById("travelDestination").textContent=command.destination||"等待目的地";
   if(command.action==="await_origin"){
    this.progress("await_origin","请先在 F2 填写常用起点，或说明从哪里出发");
    this.status("您从哪里出发？可在 F2 保存常用出发地，或说“从苏州站出发”。");return;
   }
   if(!this.config.configured){this.progress("await_config",this.config.message);return;}
   this.progress("sdk","正在连接高德地点与路线服务…");
   this.AMap=await loadAMap(this.config);
   if(version!==this.requestVersion)return;
   if(command.origin&&command.destination)await this.plan(command,version);
   else{
    this.progress("locating","正在定位城市区域…");
    const address=this.config.default_origin||"苏州市虎丘区";
    const point=await new Promise((resolve,reject)=>{
     const timer=setTimeout(()=>reject(new Error("城市位置查询超时。")),15000);
     new this.AMap.Geocoder({city:this.config.city}).getLocation(address,(status,data)=>{
      clearTimeout(timer);
      status==="complete"&&data.geocodes?.[0]?resolve(coordinates(data.geocodes[0].location)):reject(new Error("无法定位城市区域。"));
     });
    });
    if(version!==this.requestVersion)return;
    this.showScene([point],{},version);
   }
  }catch(error){if(version===this.requestVersion){
   this.progress("error",error.message+"；可重新发送导航指令重试",true);
  }}
 }
 async resolvePlace(query,role,version){
  const city=this.command.city||this.config.city||"苏州";
  this.progress("locating","正在核实"+(role==="origin"?"起点":"终点")+"："+query);
  const rows=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error("地点搜索超时："+query)),18000);
   new this.AMap.PlaceSearch({city,citylimit:true,pageSize:8,extensions:"all"}).search(query,(status,data)=>{
    clearTimeout(timer);
    status==="complete"?resolve(data.poiList?.pois||[]):reject(new Error("未在"+city+"找到可靠地点："+query));
   });
  });
  if(version!==this.requestVersion)throw new Error("请求已取消");
  const candidates=rankPlaces(query,rows,city);
  if(!candidates.length)throw new Error("未找到与“"+query+"”匹配的本市地点，请核对名称。");
  let selected=confidentPlace(candidates);
  if(!selected){
   selected=await new Promise((resolve,reject)=>{
    this.pendingPlaceReject=reject;this.controls.replaceChildren();
    this.routeBusy=false;
    this.progress("await_choice","发现同名地点，请在左侧选择"+(role==="origin"?"起点":"终点"));
    for(const candidate of candidates.slice(0,5)){
     const button=document.createElement("button");button.className="travel-choice";
     const name=document.createElement("strong"),address=document.createElement("small");
     name.textContent=candidate.name;address.textContent=candidate.city+" "+candidate.area+" "+candidate.address;
     button.append(name,address);button.onclick=()=>{
      this.pendingPlaceReject=null;this.routeBusy=true;
      this.progress("locating","已确认地点，正在继续规划…");resolve(candidate);
     };
     this.controls.append(button);
    }
   });
  }
  if(version!==this.requestVersion)throw new Error("请求已取消");
  document.getElementById(role==="origin"?"resolvedOrigin":"resolvedDestination").textContent="已定位："+selected.name+" · "+selected.city+" "+selected.area+" "+selected.address;
  return selected;
 }
 query(Planner,options,points){
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error("高德路线查询超时")),26000);
   const origin=[...points[0]],destination=[...points[1]];
   new Planner(options).search(origin,destination,(status,data)=>{
    clearTimeout(timer);
    if(status!=="complete"){reject(new Error(providerError(status,data)));return;}
    const source=coordinates(data.origin),target=coordinates(data.destination);
    if(source&&groundDistance(source,points[0])>1500||target&&groundDistance(target,points[1])>1500){
     reject(new Error("服务返回的起终点偏离已确认地点，未显示这条路线。"));return;
    }
    resolve(data);
   });
  });
 }
 async plan(command,version=this.requestVersion){
  this.routeBusy=true;this.options=[];this.path=[];this.controls.replaceChildren();
  this.state.mapReady=false;this.state.mapSummary="";this.currentContext=null;this.selected=null;
  document.getElementById("travelStatus").textContent="正在查询全部出行方式…";
  this.options=[["taxi","打车"],["driving","自驾"],["transit","公共交通"],["walking","步行"]].map(([id,label])=>({id,label,error:"正在查询…"}));
  this.renderOptions();this.options=[];
  const city=command.city||this.config.city||"苏州";
  try{
   this.progress("locating","正在核实起点与终点…");
   const origin=await this.resolvePlace(command.origin,"origin",version);
   const destination=await this.resolvePlace(command.destination,"destination",version);
   this.resolved={origin,destination};
   const points=[origin.location,destination.location];
   this.progress("routing","地点已核实，正在比较打车、自驾、公交和步行…");
   const requests=[
    this.query(this.AMap.Driving,{policy:0,extensions:"all"},points),
    this.query(this.AMap.Transfer,{city,cityd:city,policy:0},points),
    this.query(this.AMap.Walking,{},points)
   ];
   const results=await Promise.allSettled(requests);
   if(version!==this.requestVersion||!this.isOpen)return;
   const drive=results[0],transit=results[1];
   if(drive.status==="fulfilled"){
    const route=extractRoute(drive.value.routes?.[0]||{});
    const roads=[...new Set(route.steps.map(s=>s.road).filter(Boolean))].slice(0,4).join(" → ")||"按高德推荐道路行驶";
    const taxiCost=Number(drive.value.taxi_cost??(transit.status==="fulfilled"?transit.value.taxi_cost:null));
    this.options.push({id:"taxi",label:"打车",route,description:roads,
      note:"路程用时参考，不含等车"+(Number.isFinite(taxiCost)&&taxiCost>0?"；预估 "+taxiCost+" 元":"；费用以平台报价为准")});
    this.options.push({id:"driving",label:"自驾",route,description:roads,note:"高德规划用时，不含停车"});
   }else{
    for(const [id,label]of [["taxi","打车"],["driving","自驾"]])this.options.push({id,label,error:drive.reason.message});
   }
   if(transit.status==="fulfilled"){
    try{
     const plan=transit.value.plans?.[0]||{},route=extractTransit(plan);
     const description=route.steps.map(s=>s.instruction).filter(Boolean).join(" → ");
     this.options.push({id:"transit",label:"公共交通",route,description:description||"按高德公交地铁换乘方案",
      note:"含步行换乘"+(Number(plan.cost)>0?"；参考票价 "+plan.cost+" 元":"")});
    }catch(error){this.options.push({id:"transit",label:"公共交通",error:error.message});}
   }else this.options.push({id:"transit",label:"公共交通",error:transit.reason.message});
   if(results[2]?.status==="fulfilled"){
    const route=extractRoute(results[2].value.routes[0]);
    const description=[...new Set(route.steps.map(s=>s.road).filter(Boolean))].slice(0,4).join(" → ")||route.steps.slice(0,3).map(s=>s.instruction).join(" → ")||"高德步行路线";
    this.options.push({id:"walking",label:"步行",route,description,note:"高德步行用时估计"});
   }else this.options.push({id:"walking",label:"步行",error:results[2]?.reason?.message||"未返回步行方案"});
   document.getElementById("travelStatus").textContent="点击方式切换三维路线";
   this.renderOptions();
   const selected=this.options.find(o=>o.id===command.mode&&o.route)||this.options.find(o=>o.id==="driving"&&o.route)||this.options.find(o=>o.route);
   if(!selected)throw new Error(this.options.map(o=>o.label+"："+o.error).join("；"));
   this.choose(selected.id,version);
   const lines=this.options.map(option=>option.route?
    option.label+"，"+timeText(option.route.seconds)+"，"+distanceText(option.route.distance)+"。路线："+option.description+"。"+option.note+"。":
    option.label+"："+option.error+"。");
   this.api("navigation/result",{id:command.id||0,text:lines.join("\n")}).catch(()=>{});
  }finally{if(version===this.requestVersion)this.routeBusy=false;}
 }
 renderOptions(){
  this.controls.replaceChildren();
  for(const option of this.options){
   const button=document.createElement("button");button.type="button";button.className="travel-choice";button.dataset.mode=option.id;
   const title=document.createElement("strong"),detail=document.createElement("span"),note=document.createElement("small");
   title.textContent=option.label;
   detail.textContent=option.route?timeText(option.route.seconds)+" · "+distanceText(option.route.distance):"暂不可用";
   note.textContent=option.route?option.description:option.error;button.title=option.route?option.description+"\n"+option.note:option.error;
   button.setAttribute("aria-pressed",String(option.id===this.selected));
   button.append(title,detail,note);button.disabled=!option.route;button.onclick=()=>this.choose(option.id);
   this.controls.append(button);
  }
 }
 choose(id,version=this.requestVersion){
  const option=this.options.find(o=>o.id===id&&o.route);if(!option)return;
  this.selected=id;this.path=option.route.path;
  this.state.mapTrip=this.command?.origin&&this.command?.destination?(this.resolved?.origin.name||this.command.origin)+" → "+(this.resolved?.destination.name||this.command.destination):"三维粒子城市";
  this.state.mapSummary=option.label+" · "+distanceText(option.route.distance)+" · "+timeText(option.route.seconds);
  for(const button of this.controls.children){
   button.classList.toggle("selected",button.dataset.mode===id);
   button.setAttribute("aria-pressed",String(button.dataset.mode===id));
  }
  this.showScene(this.path,this.currentContext||{},version);
 }
 async showScene(path,context,version){
  if(version!==this.requestVersion||!this.isOpen)return;
  this.path=path;
  const view=this.state.cityView||"start";
  const extent=this.state.cityExtent||DEFAULT_EXTENT;
  const focus=view==="end"?(this.resolved?.destination.location||path.at(-1)):(this.resolved?.origin.location||path[0]);
  // Commit a complete scene atomically. View/route changes retain the last city while loading.
  if(context.buildings?.length){
   this.state.cityScene={path,context,view,focus,extent};this.state.cityRevision=(this.state.cityRevision||0)+1;
   this.state.mapReady=true;
  }
  this.stage.hidden=false;document.body.classList.add("map-active");
  this.progress("city","路线已就绪，正在构建三维城市…");
  document.getElementById("cityDataNote").textContent="高德路线 · 正在加载真实周边楼宇";
  try{
   const contextPath=view==="overview"?path.filter((_,i)=>i%Math.max(1,Math.ceil(path.length/1500))===0):
     [[focus[0]-extent*.8/(111320*Math.cos(focus[1]*Math.PI/180)),focus[1]-extent*.65/111320],
      [focus[0]+extent*.8/(111320*Math.cos(focus[1]*Math.PI/180)),focus[1]+extent*.65/111320]];
   const data=await this.api("city/context",{path:contextPath});
   if(version!==this.requestVersion||!this.isOpen||path!==this.path||view!==this.state.cityView)return;
   this.currentContext=data;
   this.state.cityScene={path,context:data,view,focus,extent};
   this.state.cityRevision=(this.state.cityRevision||0)+1;this.state.mapReady=true;
   this.progress("ready","路线已就绪，点击左侧方式切换");
   const note=document.getElementById("cityDataNote");
   note.textContent=data.buildings?.length?"街区矢量 · 楼高视觉强调 · "+(data.coverage==="partial"?"部分瓦片缺失 · ":""):"楼宇数据暂不可用 · ";
   const credits=[["高德","https://www.amap.com/"],["OpenFreeMap","https://openfreemap.org/"],
    ["OpenMapTiles","https://openmaptiles.org/"],["© OpenStreetMap contributors","https://www.openstreetmap.org/copyright"]];
   for(const [label,url]of credits){
    const link=document.createElement("a");link.textContent=label;link.href=url;link.target="_blank";link.rel="noopener";
    note.append(link,document.createTextNode(" "));
   }
  }catch(error){
   if(version===this.requestVersion&&this.isOpen&&path===this.path&&view===this.state.cityView){
    this.state.cityScene={path,context:{},view,focus,extent};
    this.state.cityRevision=(this.state.cityRevision||0)+1;this.state.mapReady=true;
    this.progress("ready","路线已就绪，周边楼宇暂不可用");
    document.getElementById("cityDataNote").textContent="高德真实路线 · 周边城市数据暂不可用";
   }
  }
 }
 setView(view){
  if(!["start","end","overview"].includes(view))return;
  this.state.cityView=view;resetMapView(this.state);
  for(const button of document.querySelectorAll("[data-city-view]"))button.classList.toggle("selected",button.dataset.cityView===view);
  document.getElementById("cityViewLabel").textContent=view==="overview"?"全程线路总览":view==="end"?"终点街区 · 三维城市":"起点街区 · 三维城市";
  if(this.isOpen&&this.path.length)this.showScene(this.path,{},this.requestVersion);
 }
 close(){
  if(this.pendingPlaceReject){this.pendingPlaceReject(new Error("已退出导航"));this.pendingPlaceReject=null;}
  this.isOpen=false;this.state.mapOpen=false;this.state.mapReady=false;
  this.state.mapStage="closed";this.state.mapStatus="";
  this.state.mapSummary="";this.state.mapTrip="";this.options=[];this.controls.replaceChildren();
  ++this.requestVersion;this.routeBusy=false;
  document.body.classList.remove("map-open","map-active");this.stage.hidden=true;this.panel.hidden=true;
 }
 async handle(command){
  if(command?.action==="cancel"||command?.action==="close"){this.close();return;}
  if(command?.action&&command.action!=="none")return this.open(command);
 }
}
