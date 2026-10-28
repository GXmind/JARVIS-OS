/* Pure landmark interpretation. Normalized coordinates, temporal clutch and hysteresis. */
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,(a.z||0)-(b.z||0));
const center=hand=>({x:1-(hand[0].x+hand[5].x+hand[9].x+hand[17].x)/4,y:(hand[0].y+hand[5].y+hand[9].y+hand[17].y)/4});
export function classifyHand(hand,wasPinched=false){
 if(!Array.isArray(hand)||hand.length!==21||hand.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)||Math.abs(p.x)>2||Math.abs(p.y)>2))return null;
 const size=distance(hand[0],hand[9]);if(size<.025)return null;
 const fingers=[8,12,16,20].map(t=>distance(hand[t],hand[0])>distance(hand[t-2],hand[0])*1.15&&distance(hand[t],hand[t-3])>distance(hand[t-2],hand[t-3])*1.35);
 const ratio=distance(hand[4],hand[8])/size;
 const pinch=ratio<(wasPinched?.43:.30);
 return {center:center(hand),pinch,open:!pinch&&fingers.every(Boolean),point:!pinch&&fingers[0]&&!fingers.slice(1).some(Boolean)};
}
export class HandInterpreter{
 constructor(){this.reset();this.cooldown=0;}
 reset(){this.mode=null;this.candidate=null;this.since=0;this.lastTime=null;this.anchor=null;this.filtered=null;this.previous=null;this.pinched=false;this.armed=false;}
 update(landmarks,now){
  if(this.lastTime!==null&&(now<=this.lastTime||now-this.lastTime>500))this.reset();
  this.lastTime=now;
  const hands=(landmarks||[]).map(h=>classifyHand(h,this.pinched)).filter(Boolean).sort((a,b)=>a.center.x-b.center.x);
  let mode="none",point=null,separation=null;
  if(hands.length>=2&&hands[0].pinch&&hands[1].pinch){mode="zoom";separation=Math.hypot(hands[0].center.x-hands[1].center.x,hands[0].center.y-hands[1].center.y);}
  else if(hands.length===1){const h=hands[0];point=h.center;mode=h.pinch?"pan":h.point?"orbit":h.open?"handoff":"none";this.pinched=h.pinch;}
  else this.pinched=false;
  const actions=[];
  if(mode!==this.candidate){
   if(this.mode==="pan"||this.mode==="zoom")actions.push({type:"end",commit:true});
   this.mode=null;this.candidate=mode;this.since=now;this.previous=null;this.filtered=null;this.anchor=point;this.armed=false;
   return actions;
  }
  if(mode==="none"||now-this.since<180)return actions;
  this.mode=mode;
  if(mode==="zoom"){
   if(separation<.04)return actions;
   const value=this.filtered===null?separation:this.filtered*.65+separation*.35;
   if(this.previous!==null){const factor=value/this.previous;if(Math.abs(Math.log(factor))>.003)actions.push({type:"zoom",factor:Math.max(.85,Math.min(1.18,factor))});}
   this.filtered=value;this.previous=value;return actions;
  }
  const value=this.filtered?{x:this.filtered.x*.65+point.x*.35,y:this.filtered.y*.65+point.y*.35}:point;
  if(mode==="handoff"){
   if(!this.armed&&Math.hypot(point.x-this.anchor.x,point.y-this.anchor.y)>.10){this.since=now;this.anchor=point;}
   if(now-this.since>=700)this.armed=true;
   const dx=point.x-this.anchor.x,dy=point.y-this.anchor.y;
   if(this.armed&&now>=this.cooldown&&Math.max(Math.abs(dx),Math.abs(dy))>.22&&Math.min(Math.abs(dx),Math.abs(dy))<.18){
    actions.push({type:"handoff",direction:Math.abs(dx)>=Math.abs(dy)?(dx>0?"right":"left"):(dy>0?"down":"up")});this.cooldown=now+2500;this.since=now;this.anchor=point;this.armed=false;
   }
  }else if(this.previous){
   const dx=value.x-this.previous.x,dy=value.y-this.previous.y;
   if(Math.hypot(dx,dy)>.0025){actions.push({type:mode,dx:Math.max(-.06,Math.min(.06,dx)),dy:Math.max(-.06,Math.min(.06,dy))});this.previous=value;}
  }
  this.filtered=value;if(!this.previous||mode==="handoff")this.previous=value;
  return actions;
 }
}
