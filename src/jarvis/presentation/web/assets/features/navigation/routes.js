/* Pure provider-result geometry and saved-origin resolution. */
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
