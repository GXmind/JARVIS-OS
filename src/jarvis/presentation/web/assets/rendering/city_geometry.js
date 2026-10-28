import {DEFAULT_EXTENT,DEFAULT_HEIGHT_SCALE,routeFrame} from "../features/map/controls.js";
/* Accurate source coordinates, polygon courtyards and independently exaggerated architecture. */
export function inside(point,ring){
 let yes=false;
 for(let i=0,j=ring.length-1;i<ring.length;j=i++){
  const a=ring[i],b=ring[j];
  if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes;
 }return yes;
}
export function clipSegment(a,b,bounds){
 const dx=b[0]-a[0],dy=b[1]-a[1],p=[-dx,dx,-dy,dy],q=[a[0]+bounds[0],bounds[0]-a[0],a[1]+bounds[1],bounds[1]-a[1]];
 let low=0,high=1;
 for(let i=0;i<4;i++){
  if(Math.abs(p[i])<1e-12){if(q[i]<0)return null;continue;}
  const t=q[i]/p[i];if(p[i]<0)low=Math.max(low,t);else high=Math.min(high,t);
  if(low>high)return null;
 }
 return [[a[0]+low*dx,a[1]+low*dy],[a[0]+high*dx,a[1]+high*dy]];
}
export function buildCityPositions(data,path,view="start",focus=null,options={}){
 const basis=path.length?path:(data.roads?.[0]?.path||data.buildings?.[0]?.footprint||[]);
 const empty={points:[],colors:[],fades:[],edges:[],streets:[],arterials:[],paths:[],route:[],routeParts:[],labels:[],origin:[0,0],scale:1,renderedBuildings:0};
 if(!basis.length)return empty;
 const overview=view==="overview",localExtent=Math.max(400,Math.min(5000000,Number(options.extent)||DEFAULT_EXTENT));
 const frame=routeFrame(basis,localExtent);
 const origin=overview?frame.origin:(focus||(view==="end"?basis.at(-1):basis[0]));
 const cos=Math.cos(origin[1]*Math.PI/180),meters=p=>[(p[0]-origin[0])*111320*cos,(p[1]-origin[1])*111320];
 const routeM=basis.map(meters),extent=overview?frame.extent:localExtent;
 const scale=3.9/extent,bounds=[2.4/scale,1.6/scale],heightScale=Math.max(1,Math.min(32,Number(options.heightScale)||DEFAULT_HEIGHT_SCALE));
 const particleBudget=Math.max(8000,Math.min(36000,Number(options.particleBudget)||36000));
 const points=[],colors=[],fades=[],edges=[],streets=[],arterials=[],paths=[],route=[],routeParts=[],labels=[];
 let quota=36000,used=0,visualMaxHeight=0;
 function put(x,y,z,color){
  if(points.length>=particleBudget*3||used>=quota||Math.abs(x)>bounds[0]||Math.abs(z)>bounds[1])return;
  const fade=Math.max(.05,1-Math.max(Math.abs(x)/bounds[0],Math.abs(z)/bounds[1])**8);
  points.push(x*scale,y*scale,-z*scale);colors.push(...color);fades.push(fade);used++;
 }
 function edge(a,b,height){
  const clipped=clipSegment(a,b,bounds);if(!clipped||edges.length>=360000)return;
  for(const p of clipped)edges.push(p[0]*scale,height*scale,-p[1]*scale);
 }
 function grains(a,b,height,color,spacing=4){
  const clipped=clipSegment(a,b,bounds);if(!clipped)return;
  [a,b]=clipped;const count=Math.min(240,Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/spacing)));
  for(let i=0;i<count;i++){const t=i/count;put(a[0]+(b[0]-a[0])*t,height,a[1]+(b[1]-a[1])*t,color);}
 }
 const buildings=(data.buildings||[]).map(building=>{
  const ring=building.footprint.map(meters),x=ring.map(p=>p[0]),z=ring.map(p=>p[1]);
  const distance=ring.reduce((s,p)=>s+Math.hypot(...p),0)/ring.length;
  return {building,ring,distance,xmin:Math.min(...x),xmax:Math.max(...x),zmin:Math.min(...z),zmax:Math.max(...z)};
 }).filter(b=>b.xmin<bounds[0]&&b.xmax>-bounds[0]&&b.zmin<bounds[1]&&b.zmax>-bounds[1]).sort((a,b)=>a.distance-b.distance);
 if(!overview){
  quota=Math.max(12,Math.floor(particleBudget/Math.max(1,buildings.length)));
  for(const item of buildings){
   used=0;
   const {building,ring}=item,holes=(building.holes||[]).map(h=>h.map(meters));
   const realHeight=Math.min(500,Math.max(3,Number(building.height)||12));
   // Keep very tall source towers on screen without modifying the source height.
   const h=Math.min(realHeight*heightScale,1.7/scale),bottom=Math.max(0,Number(building.min_height)||0)/realHeight*h;
   visualMaxHeight=Math.max(visualMaxHeight,h*scale);
   for(const wall of [ring,...holes])for(let i=1;i<wall.length;i++){
    const a=wall[i-1],b=wall[i];
    edge(a,b,h);edge(a,b,bottom);grains(a,b,h,[.55,.73,.80]);
    const clipped=clipSegment(a,b,bounds);if(!clipped)continue;
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]),count=Math.max(1,Math.min(20,Math.ceil(length/6)));
    const shade=.45+.35*Math.abs((b[0]-a[0])/(length||1));
    for(let j=0;j<=count&&used<quota;j++){
     const t=j/count,x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;
     for(let y=bottom;y<h&&used<quota;y+=Math.max(8,(h-bottom)/10))put(x,y,z,[.22*shade,.40*shade,.52*shade]);
    }
    if(Math.abs(a[0])<bounds[0]&&Math.abs(a[1])<bounds[1]&&edges.length<360000)
     edges.push(a[0]*scale,bottom*scale,-a[1]*scale,a[0]*scale,h*scale,-a[1]*scale);
   }
   const xmin=Math.max(-bounds[0],item.xmin),xmax=Math.min(bounds[0],item.xmax);
   const zmin=Math.max(-bounds[1],item.zmin),zmax=Math.min(bounds[1],item.zmax);
   const step=Math.max(5,Math.sqrt(Math.max(1,(xmax-xmin)*(zmax-zmin))/20));
   for(let x=xmin;x<xmax&&used<quota;x+=step)for(let z=zmin;z<zmax&&used<quota;z+=step)
    if(inside([x,z],ring)&&!holes.some(hole=>inside([x,z],hole)))put(x,h,z,[.30,.47,.57]);
  }
 }
 {
  for(const road of data.roads||[]){
   if(["ferry","aerialway"].includes(road.kind))continue;
   const path=road.path.map(meters),major=/^(motorway|trunk|primary|secondary|tertiary)$/.test(road.kind);
   const pedestrian=/path|footway|pedestrian|cycleway|steps|track/.test(road.kind+" "+(road.subclass||""));
   const target=major?arterials:pedestrian?paths:streets;
   for(let i=1;i<path.length;i++){
    const clipped=clipSegment(path[i-1],path[i],bounds);if(!clipped)continue;
    for(const p of clipped)target.push(p[0]*scale,.002,-p[1]*scale);
   }
  }
  for(const label of data.labels||[]){
   const [x,z]=meters(label.location);
   if(Math.abs(x*scale)>2.15||Math.abs(z*scale)>1.3||labels.some(p=>p.name===label.name||Math.hypot(p.position[0]-x*scale,p.position[2]+z*scale)<.42))continue;
   labels.push({name:label.name,position:[x*scale,.035,-z*scale]});if(labels.length>=8)break;
  }
 }
 // Keep the entire provider route in the scene. The camera clips visibility, never the data.
 const totalLength=routeM.slice(1).reduce((sum,p,i)=>sum+Math.hypot(p[0]-routeM[i][0],p[1]-routeM[i][1]),0);
 const spacing=Math.max(2,totalLength/7500);
 const fullLine=[];
 for(let i=1;i<routeM.length;i++){
  const a=routeM[i-1],b=routeM[i],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
  fullLine.push(a[0]*scale,3*scale,-a[1]*scale,b[0]*scale,3*scale,-b[1]*scale);
  const count=Math.max(1,Math.ceil(length/spacing)),part=[];
  for(let j=0;j<=count;j++){
   const t=j/count,p=[(a[0]+(b[0]-a[0])*t)*scale,3*scale,-(a[1]+(b[1]-a[1])*t)*scale];
   const last=route.at(-1);if(!last||Math.hypot(...p.map((v,k)=>v-last[k]))>.001)route.push(p);
   part.push(p);
  }
  if(part.length>1)routeParts.push(part);
 }
 return {points,colors,fades,edges,streets,arterials,paths,labels,route,routeParts,origin,scale,extent,bounds,
  renderedBuildings:overview?0:buildings.length,visualMaxHeight,heightScale,fullLine};
}
