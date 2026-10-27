export const DEFAULT_EXTENT=1600;
export const DEFAULT_HEIGHT_SCALE=16;
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function resetMapView(state){
 state.cityYaw=0;state.cityPitch=.62;state.cityZoom=1;state.cityPanX=0;state.cityPanY=0;
}
export function orbitView(state,dx,dy,start=state){
 const yaw=Number(start.cityYaw)||0,pitch=Number(start.cityPitch)||.62;
 state.cityYaw=yaw+dx*.006; // Intentionally unbounded: repeated complete revolutions are supported.
 state.cityPitch=clamp(pitch+dy*.0045,.08,1.45);
}
export function panView(state,dx,dy,start=state){
 const zoom=Number(start.cityZoom)||1;
 state.cityPanX=clamp((Number(start.cityPanX)||0)+dx*.006/zoom,-2.2,2.2);
 state.cityPanY=clamp((Number(start.cityPanY)||0)-dy*.006/zoom,-1.6,1.6);
}
export function zoomView(state,delta){state.cityZoom=clamp((Number(state.cityZoom)||1)*Math.exp(-delta*.001),.45,4);}
export function bindMapControls(canvas,state){
 const pointers=new Map();let gesture=null;
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
  if(!state.mapReady)return;
  if(event.button!==0&&event.button!==2&&event.pointerType!=="touch")return;
  event.preventDefault();
  pointers.set(event.pointerId,{x:event.clientX,y:event.clientY,pan:event.button===2||event.shiftKey});
  canvas.setPointerCapture(event.pointerId);begin();
 });
 canvas.addEventListener("pointermove",event=>{
  if(!pointers.has(event.pointerId)||!gesture)return;
  pointers.set(event.pointerId,{...pointers.get(event.pointerId),x:event.clientX,y:event.clientY});
  if(!state.mapReady){pointers.clear();gesture=null;return;}
  if(gesture.kind==="pinch"){
   const p=[...pointers.values()];if(p.length<2)return;
   const distance=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);
   state.cityZoom=clamp(gesture.start.cityZoom*distance/Math.max(1,gesture.distance),.45,4);
   panView(state,(p[0].x+p[1].x)/2-gesture.x,(p[0].y+p[1].y)/2-gesture.y,gesture.start);
  }else{
   const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
   (gesture.kind==="pan"?panView:orbitView)(state,dx,dy,gesture.start);
  }
 });
 const end=event=>{
  pointers.delete(event.pointerId);
  if(canvas.hasPointerCapture?.(event.pointerId))canvas.releasePointerCapture(event.pointerId);
  begin();
 };
 canvas.addEventListener("pointerup",end);canvas.addEventListener("pointercancel",end);
 canvas.addEventListener("lostpointercapture",event=>{pointers.delete(event.pointerId);begin();});
 canvas.addEventListener("contextmenu",event=>{if(state.mapReady)event.preventDefault();});
 canvas.addEventListener("wheel",event=>{if(state.mapReady){event.preventDefault();zoomView(state,event.deltaY);}},{passive:false});
 canvas.addEventListener("dblclick",event=>{if(state.mapReady){event.preventDefault();resetMapView(state);}});
 return {reset:()=>resetMapView(state)};
}
