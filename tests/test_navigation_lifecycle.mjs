import assert from "node:assert/strict";
import {NavigationController} from "../src/jarvis/presentation/web/assets/features/navigation/controller.js";
class Element{
 constructor(){this.children=[];this.textContent="";this.hidden=false;this.classList={add(){},remove(){},toggle(){}};}
 replaceChildren(...nodes){this.children=nodes;} append(...nodes){this.children.push(...nodes);}
}
const elements=new Map();
globalThis.document={body:new Element(),querySelectorAll:()=>[],createTextNode:text=>text,createElement:()=>new Element(),getElementById:id=>{
 if(!elements.has(id))elements.set(id,new Element());return elements.get(id);
}};
const row=(id,location=[120.62,31.32])=>({id,name:"同名公园",cityname:"苏州市",type:"风景名胜;公园",location});
function controller(rows){
 const n=new NavigationController({api:async()=>({}),state:{},message(){},openSettings(){}});
 n.isOpen=true;n.requestVersion=1;n.command={city:"苏州"};n.config={city:"苏州"};n.routeBusy=true;
 n.AMap={PlaceSearch:class{search(_query,cb){cb("complete",{poiList:{pois:rows}});}}};
 return n;
}
const n=controller([row("a"),row("b",[120.68,31.36])]);
const pending=n.resolvePlace("同名公园","destination",1);
await Promise.resolve();
assert.equal(n.state.mapStage,"await_choice");assert.equal(n.routeBusy,false);
assert.match(n.state.mapStatus,/左侧选择终点/);
assert.equal(n.controls.children.length,2);
n.controls.children[1].onclick();
assert.equal((await pending).id,"b");assert.equal(n.pendingPlaceReject,null);assert.equal(n.routeBusy,true);
const c=controller([row("a"),row("b",[120.68,31.36])]);
const cancelled=c.resolvePlace("同名公园","destination",1);
await Promise.resolve();c.close();
await assert.rejects(cancelled,/退出导航/);
assert.equal(c.state.mapStage,"closed");assert.equal(c.routeBusy,false);
assert.equal(c.controls.children.length,0);
console.log("Ambiguous-place prompt, continuation and cancellation lifecycle passed.");

const browse=controller([]),responses=[];
browse.state.mapReady=true;browse.state.cityView="browse";browse.state.cityFocus=[120.6,31.31];
browse.api=()=>new Promise(resolve=>responses.push(resolve));
const route=[[120.6,31.31],[120.7,31.32]];
const first=browse.showScene(route,{},1);
browse.state.cityFocus=[120.65,31.315];
const discarded=browse.showScene(route,{},1);
browse.state.cityFocus=[120.7,31.32];
const latest=browse.showScene(route,{},1);
assert.equal(responses.length,1,"Only one city request may be in flight");
responses[0]({buildings:[],roads:[],marker:"old-area"});await first;await discarded;
await Promise.resolve();
assert.equal(responses.length,2,"Intermediate queued views must be coalesced, not all downloaded");
responses[1]({buildings:[],roads:[],marker:"new-area"});await latest;
assert.equal(browse.state.cityScene.context.marker,"new-area");
assert.deepEqual(browse.state.cityScene.focus,[120.7,31.32]);
assert.equal(browse.contextLoading,false);
console.log("Map loads are serialized, intermediate views coalesce and old responses cannot restore old areas.");
