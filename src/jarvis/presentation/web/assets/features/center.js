/* Dedicated model controls use existing central canvas; no new panels. */
export function bindCenterControls(canvas,state){
 let drag=null;
 const active=()=>state.center?.active&&!state.mapReady;
 canvas.addEventListener("pointerdown",event=>{if(!active()||event.button!==0)return;drag={x:event.clientX,y:event.clientY};canvas.setPointerCapture?.(event.pointerId);});
 canvas.addEventListener("pointermove",event=>{if(!drag||!active())return;state.centerYaw=(state.centerYaw||0)+(event.clientX-drag.x)*.006;state.centerPitch=Math.max(-1.4,Math.min(1.4,(state.centerPitch||.15)+(event.clientY-drag.y)*.004));drag={x:event.clientX,y:event.clientY};});
 for(const name of ["pointerup","pointercancel","lostpointercapture"])canvas.addEventListener(name,()=>drag=null);
 canvas.addEventListener("wheel",event=>{if(!active())return;event.preventDefault();state.centerZoom=Math.max(.5,Math.min(2.5,(state.centerZoom||1)*Math.exp(-event.deltaY*.001)));},{passive:false});
 canvas.addEventListener("dblclick",()=>{if(active()){state.centerYaw=0;state.centerPitch=.15;state.centerZoom=1;}});
}
