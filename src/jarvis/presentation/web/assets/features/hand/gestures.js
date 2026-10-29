/* Scale/rotation invariant joints and a multi-sample natural swipe, without a long hold. */
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,(a.z||0)-(b.z||0));
const center=h=>({x:1-(h[0].x+h[5].x+h[9].x+h[17].x)/4,y:(h[0].y+h[5].y+h[9].y+h[17].y)/4});
function angle(a,b,c){const u=[a.x-b.x,a.y-b.y,(a.z||0)-(b.z||0)],v=[c.x-b.x,c.y-b.y,(c.z||0)-(b.z||0)];return Math.acos(Math.max(-1,Math.min(1,u.reduce((s,x,i)=>s+x*v[i],0)/(Math.hypot(...u)*Math.hypot(...v)||1))));}
export function classifyHand(hand,wasPinched=false,world=null){
 if(!Array.isArray(hand)||hand.length!==21||hand.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)||Math.abs(p.x)>2||Math.abs(p.y)>2))return null;
 const imageSize=distance(hand[0],hand[9]);if(imageSize<.025)return null;
 const h=world?.length===21?world:hand,size=distance(h[0],h[9]);if(size<.01)return null;
 const fingers=[8,12,16,20].map(t=>angle(h[t-3],h[t-2],h[t-1])>2.35&&angle(h[t-2],h[t-1],h[t])>2.25&&distance(h[t],h[0])>distance(h[t-2],h[0])*1.04);
 const pinch=distance(h[4],h[8])/size<(wasPinched?.45:.32),extended=fingers.filter(Boolean).length;
 return {center:center(hand),size:imageSize,pinch,open:!pinch&&extended>=3&&fingers[1]&&fingers[2],point:!pinch&&fingers[0]&&extended<=2};
}
export class HandInterpreter{
 constructor(){this.cooldown=0;this.reset();}
 reset(){this.mode=null;this.candidate=null;this.since=0;this.lastTime=null;this.filtered=null;this.previous=null;this.lastHands=[];this.missing=null;this.history=[];this.hint="等待手进入画面";}
 update(landmarks,now,world=[]){
  let dt=this.lastTime===null?.1:(now-this.lastTime)/1000;
  if(this.lastTime!==null&&(dt<=0||dt>1)){this.reset();dt=.1;}
  this.lastTime=now;
  const hands=(landmarks||[]).map((hand,i)=>{
   if(!Array.isArray(hand)||hand.length!==21)return null;
   const c=center(hand),previous=this.lastHands.find(h=>Math.hypot(h.center.x-c.x,h.center.y-c.y)<.2);
   return classifyHand(hand,!!previous?.pinch,world[i]);
  }).filter(Boolean).sort((a,b)=>a.center.x-b.center.x);this.lastHands=hands;
  let mode="none",point=null,separation=null;
  if(hands.length>=2&&hands[0].pinch&&hands[1].pinch){mode="zoom";separation=Math.hypot(hands[0].center.x-hands[1].center.x,hands[0].center.y-hands[1].center.y);}
  else if(hands.length===1){const h=hands[0];point=h.center;mode=h.pinch?"pan":h.point?"orbit":h.open?"handoff":"none";}
  const actions=[];
  if(mode==="none"&&this.candidate&&this.candidate!=="none"){
   if(this.missing===null)this.missing=now;
   if(now-this.missing<220){this.hint="保持手势，正在跟踪";return actions;}
  }else this.missing=null;
  if(mode!==this.candidate){
   if(this.mode==="pan"||this.mode==="zoom")actions.push({type:"end",commit:true});
   this.mode=null;this.candidate=mode;this.since=now;this.previous=null;this.filtered=null;this.history=point?[{...point,time:now}]:[];
   return actions;
  }
  if(mode==="none"){this.hint="张掌划向目标屏 · 捏合拖动 · 食指旋转";return actions;}
  if(now-this.since<120)return actions;
  this.mode=mode;
  const alpha=Math.max(.3,Math.min(.88,1-Math.exp(-Math.max(.03,dt)/.065)));
  if(mode==="zoom"){
   this.hint="双手捏合开合：缩放";if(separation<.04)return actions;
   const value=this.filtered===null?separation:this.filtered*(1-alpha)+separation*alpha;
   if(this.previous!==null){const factor=value/this.previous;if(Math.abs(Math.log(factor))>.003)actions.push({type:"zoom",factor:Math.max(.85,Math.min(1.18,factor))});}
   this.filtered=value;this.previous=value;return actions;
  }
  const value=this.filtered?{x:this.filtered.x*(1-alpha)+point.x*alpha,y:this.filtered.y*(1-alpha)+point.y*alpha}:point;
  if(mode==="handoff"){
   this.hint="张掌已就绪，朝目标屏幕划动";
   const last=this.history.at(-1),step=last?Math.hypot(point.x-last.x,point.y-last.y)/Math.max(.05,(now-last.time)/1000):0;
   if(step>2.8){this.history=[{...point,time:now}];return actions;}
   this.history.push({...point,time:now});this.history=this.history.filter(p=>now-p.time<850);
   if(this.history.length>=3&&now>=this.cooldown){
    const first=this.history[0],dx=point.x-first.x,dy=point.y-first.y,duration=(now-first.time)/1000;
    const major=Math.max(Math.abs(dx),Math.abs(dy)),minor=Math.min(Math.abs(dx),Math.abs(dy)),threshold=Math.max(.12,Math.min(.20,hands[0].size*.85));
    const path=this.history.slice(1).reduce((s,p,i)=>s+Math.hypot(p.x-this.history[i].x,p.y-this.history[i].y),0);
    if(duration>=.18&&major>threshold&&minor<Math.max(.08,major*.58)&&major/duration>.24&&Math.hypot(dx,dy)/Math.max(.01,path)>.72){
     actions.push({type:"handoff",direction:Math.abs(dx)>=Math.abs(dy)?(dx>0?"right":"left"):(dy>0?"down":"up")});this.cooldown=now+2300;this.history=[{...point,time:now}];this.hint="正在传送地图";
    }
   }
  }else if(this.previous){
   this.hint=mode==="pan"?"捏合拖动地图":"食指移动：旋转地图";
   const dx=value.x-this.previous.x,dy=value.y-this.previous.y;
   if(Math.hypot(dx,dy)>.002){actions.push({type:mode,dx:Math.max(-.06,Math.min(.06,dx)),dy:Math.max(-.06,Math.min(.06,dy))});this.previous=value;}
  }
  this.filtered=value;if(!this.previous||mode==="handoff")this.previous=value;
  return actions;
 }
}
