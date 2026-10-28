export const VIEW_KEYS=["cityYaw","cityPitch","cityZoom","cityPanX","cityPanY"];
export const DEFAULT_EXTENT=1600;
export const DEFAULT_HEIGHT_SCALE=16;
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function resetMapView(state){
 state.cityYaw=0;state.cityPitch=.62;state.cityZoom=1;state.cityPanX=0;state.cityPanY=0;
 state.cityDragMode=state.cityDragMode||"pan";
}
export function orbitView(state,dx,dy,start=state){
 const yaw=Number(start.cityYaw)||0,pitch=Number(start.cityPitch)||.62;
 state.cityYaw=yaw+dx*.006; // Intentionally unbounded: repeated complete revolutions are supported.
 state.cityPitch=clamp(pitch+dy*.0045,.08,1.45);
}
export function panView(state,dx,dy,start=state){
 state.cityPanX=(Number(start.cityPanX)||0)+dx*.006;
 state.cityPanY=(Number(start.cityPanY)||0)-dy*.006;
}
export function zoomView(state,delta){state.cityZoom=clamp((Number(state.cityZoom)||1)*Math.exp(-delta*.001),.45,4);}
export function routeFrame(path,minimum=DEFAULT_EXTENT){
 const xs=path.map(p=>p[0]),ys=path.map(p=>p[1]);
 if(!path.length)return {origin:[0,0],extent:minimum};
 const origin=[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2];
 const width=(Math.max(...xs)-Math.min(...xs))*111320*Math.cos(origin[1]*Math.PI/180);
 const depth=(Math.max(...ys)-Math.min(...ys))*111320;
 return {origin,extent:Math.max(minimum,width*3.9/3.3,depth*3.9/2.2)*1.16};
}
export function rebaseMapView(state,frame){
 const zoom=Number(state.cityZoom)||1,scale=3.9/frame.extent;
 const yaw=-.25+(Number(state.cityYaw)||0),pitch=Number(state.cityPitch)||.62;
 const tx=Number(state.cityPanX)||0,ty=Number(state.cityPanY)||0;
 const sp=Math.max(.2,Math.sin(pitch)),cy=Math.cos(yaw),sy=Math.sin(yaw);
 const east=(-cy*tx-sy*ty/sp)/(.88*zoom*scale);
 const north=-(-sy*tx+cy*ty/sp)/(.88*zoom*scale);
 const origin=frame.origin;
 return {origin:[clamp(origin[0]+east/(111320*Math.cos(origin[1]*Math.PI/180)),73.01,135.99),
  clamp(origin[1]+north/111320,18.01,53.99)],extent:clamp(frame.extent/zoom,400,5000000)};
}
export function bindMapControls(canvas,state,options={}){
 const pointers=new Map();let gesture=null,panDirty=false;
 const snapshot=()=>({...state});
 function begin(){
  const points=[...pointers.values()];
  if(points.length>1){
   gesture={kind:"pinch",start:snapshot(),distance:Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y),
    x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2};
  }else if(points.length)gesture={kind:points[0].pan?"pan":"orbit",...points[0],start:snapshot()};
  else gesture=null;
 }
 canvas.addEventListener("pointerdown",event=>{
  if(!state.mapReady||state.mapDetached)return;
  if(event.button!==0&&event.button!==2&&event.pointerType!=="touch")return;
  event.preventDefault();
  pointers.set(event.pointerId,{x:event.clientX,y:event.clientY,pan:event.button!==2&&!event.shiftKey&&state.cityDragMode!=="orbit"});
  canvas.setPointerCapture(event.pointerId);begin();
 });
 canvas.addEventListener("pointermove",event=>{
  if(!pointers.has(event.pointerId)||!gesture)return;
  pointers.set(event.pointerId,{...pointers.get(event.pointerId),x:event.clientX,y:event.clientY});
  if(!state.mapReady||state.mapDetached){pointers.clear();gesture=null;return;}
  if(gesture.kind==="pinch"){
   const p=[...pointers.values()];if(p.length<2)return;
   const distance=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);
   state.cityZoom=clamp(gesture.start.cityZoom*distance/Math.max(1,gesture.distance),.45,4);
   panView(state,(p[0].x+p[1].x)/2-gesture.x,(p[0].y+p[1].y)/2-gesture.y,gesture.start);panDirty=true;
  }else{
   const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
   (gesture.kind==="pan"?panView:orbitView)(state,dx,dy,gesture.start);
   if(gesture.kind==="pan")panDirty=true;
  }
 });
 const end=event=>{
  pointers.delete(event.pointerId);
  if(canvas.hasPointerCapture?.(event.pointerId))canvas.releasePointerCapture(event.pointerId);
  begin();
  if(!pointers.size&&panDirty){panDirty=false;options.onViewEnd?.();}
 };
 canvas.addEventListener("pointerup",end);canvas.addEventListener("pointercancel",end);
 canvas.addEventListener("lostpointercapture",event=>{pointers.delete(event.pointerId);begin();});
 canvas.addEventListener("contextmenu",event=>{if(state.mapReady)event.preventDefault();});
 canvas.addEventListener("wheel",event=>{if(state.mapReady&&!state.mapDetached){event.preventDefault();zoomView(state,event.deltaY);options.onZoom?.();}},{passive:false});
 canvas.addEventListener("dblclick",event=>{if(state.mapReady&&!state.mapDetached){event.preventDefault();resetMapView(state);}});
 return {reset:()=>resetMapView(state)};
}
