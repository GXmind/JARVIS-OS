import assert from "node:assert/strict";
import {buildCenter} from "../src/jarvis/presentation/web/assets/rendering/center_geometry.js";
import {visualActivity} from "../src/jarvis/presentation/web/assets/rendering/activity.js";
for(const shape of ["sphere","box","torus","cone","cylinder","helix","heart","galaxy","wave","text"]){
 const result=buildCenter({nodes:[{shape,position:[0,0,0],scale:[1,1,1]}]},16000);assert.equal(result.count,16000);assert(result.positions.every(Number.isFinite));assert(Math.max(...result.positions)<=1.71);assert(result.colors.every(x=>x>=0&&x<=1));
}
const p={nodes:[{shape:"box",position:[-1,0,0],scale:[.5,1,1]},{shape:"sphere",position:[1,0,0],scale:[.5,.5,.5]}]};
assert.deepEqual(buildCenter(p,12000).positions,buildCenter(p,12000).positions);assert.equal(buildCenter(p,1000000).count,24000);
for(const [activity,code]of [["idle",0],["listening",1],["transcribing",2],["thinking",3],["speaking",4],["modeling",5]])assert.equal(visualActivity({activity}).code,code);
assert.equal(visualActivity({activity:"speaking",mapReady:true}).name,"dedicated");assert.equal(visualActivity({activity:"thinking",center:{active:true}}).code,0);
console.log("All primitive point clouds are finite, bounded, deterministic; maps/models suppress dialogue forms.");

const free=[{shape:"curve",points:[[0,0,0],[1,1,0],[-1,2,.5]],radius:.03},{shape:"lathe",profile:[[0,-1],[.7,0],[.3,1]]},{shape:"patch",control:Array.from({length:16},(_,i)=>[i%4/3,i>>2,Math.sin(i)*.2])},{shape:"mesh",vertices:[[0,0,0],[1,0,0],[0,1,0]],faces:[[0,1,2]]},{shape:"drawing",color:"#00ff00"}];
for(const node of free){const data=buildCenter({nodes:[node]},12000,{0:[[-.5,0,0,1,0],[.5,1,0,1,0]]});assert(data.positions.every(Number.isFinite),node.shape);assert.equal(data.count,12000);}
console.log("Arbitrary paths, free curves, lathed profiles, Bezier patches, indexed meshes and custom colors passed.");

const {sampleTrack}=await import("../src/jarvis/presentation/web/assets/rendering/animation.js");
const track={frames:[{t:0,move:[0,0,0],turn:[0,0,0],stretch:[1,1,1]},{t:2,move:[2,0,0],turn:[0,0,1],stretch:[2,2,2]}]};
assert.deepEqual(sampleTrack(track,1).move,[1,0,0]);assert.deepEqual(sampleTrack(track,3).move,[1,0,0]);assert.deepEqual(sampleTrack({...track,loop:false},5).move,[2,0,0]);
console.log("Free per-part keyframe motion, interpolation and looping passed.");

const quadratic=buildCenter({nodes:[{shape:"patch",rows:3,cols:3,control:Array.from({length:9},(_,i)=>[i%3,i/3|0,Math.sin(i)*.2])}]},12000);assert(quadratic.positions.every(Number.isFinite));console.log("Variable-degree free Bezier control grids passed.");
