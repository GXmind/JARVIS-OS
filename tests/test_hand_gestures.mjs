import assert from "node:assert/strict";
import {classifyHand,HandInterpreter} from "../src/jarvis/presentation/web/assets/features/hand/gestures.js";
function hand(pose="open",dx=0,dy=0){
 const h=Array.from({length:21},()=>({x:.5,y:.7,z:0}));h[0]={x:.5,y:.88,z:0};
 for(let f=0;f<4;f++){
  const m=5+f*4,x=.38+f*.08,y=.61+Math.abs(f-1)*.025,extended=pose==="open"||pose==="point"&&f===0;
  h[m]={x,y,z:0};h[m+1]={x,y:y-.09,z:0};h[m+2]={x,y:extended?y-.20:y-.035,z:0};h[m+3]={x,y:extended?y-.31:y+.055,z:0};
 }
 h[1]={x:.38,y:.79,z:0};h[2]={x:.29,y:.70,z:0};h[3]={x:.23,y:.63,z:0};h[4]={x:.19,y:.58,z:0};
 if(pose==="pinch")h[4]={x:h[8].x+.018,y:h[8].y,z:0};
 return h.map(p=>({...p,x:p.x+dx,y:p.y+dy}));
}
assert(classifyHand(hand("open")).open);assert(classifyHand(hand("point")).point);assert(classifyHand(hand("pinch")).pinch);
assert.equal(classifyHand([]),null);assert.equal(classifyHand(hand().map(p=>({...p,x:NaN}))),null);
let engine=new HandInterpreter();assert.deepEqual(engine.update([hand("pinch")],0),[]);assert.deepEqual(engine.update([hand("pinch")],100),[]);
engine.update([hand("pinch")],220);let actions=[];
for(let i=1;i<12;i++)actions.push(...engine.update([hand("pinch",-i*.01)],220+i*100));
assert(actions.some(a=>a.type==="pan"&&a.dx>0));assert(actions.every(a=>!a.dx||Math.abs(a.dx)<=.06));
assert(engine.update([],1500).some(a=>a.type==="end"));assert.deepEqual(engine.update([],1600),[]);
engine=new HandInterpreter();engine.update([hand("point")],0);engine.update([hand("point")],220);
assert(engine.update([hand("point",-.04,.03)],320).some(a=>a.type==="orbit"&&a.dy>0));
engine=new HandInterpreter();engine.update([hand("pinch",-.14),hand("pinch",.14)],0);engine.update([hand("pinch",-.14),hand("pinch",.14)],220);
assert(engine.update([hand("pinch",-.19),hand("pinch",.19)],320).some(a=>a.type==="zoom"&&a.factor>1));
assert(engine.update([hand("pinch",-.11),hand("pinch",.11)],420).some(a=>a.type==="zoom"&&a.factor<1));
engine=new HandInterpreter();engine.update([hand()],0);engine.update([hand()],200);
assert.deepEqual(engine.update([hand("open",-.3)],300),[],"Fast unarmed swipes must not split the screen");
engine=new HandInterpreter();engine.update([hand()],0);
for(let t=100;t<=800;t+=100)assert.deepEqual(engine.update([hand()],t),[]);
assert(engine.update([hand("open",-.25)],900).some(a=>a.type==="handoff"&&a.direction==="right"));
assert(!engine.update([hand("open",.25)],1200).some(a=>a.type==="handoff"),"Handoff has a cooldown");
assert.deepEqual(engine.update([hand("pinch")],2400),[],"Tracking gap must reset anchors");
console.log("Pinch pan, index orbit, two-hand zoom, clutch dwell, release, tracking loss and deliberate handoff passed.");
for(const [dy,direction]of [[.26,"down"],[-.26,"up"]]){
 const e=new HandInterpreter();for(let time=0;time<=800;time+=100)e.update([hand()],time);
 assert(e.update([hand("open",0,dy)],900).some(a=>a.type==="handoff"&&a.direction===direction));
}
console.log("Transfer swipe supports screen directions left/right/up/down.");
