import assert from "node:assert/strict";
import {HandCamera} from "../src/jarvis/presentation/web/assets/features/hand/camera.js";
const listeners={},frames=[];
globalThis.document={hidden:false,addEventListener:(name,fn)=>listeners[name]=fn};globalThis.addEventListener=()=>{};
globalThis.requestAnimationFrame=fn=>(frames.push(fn),frames.length);globalThis.cancelAnimationFrame=()=>{};
let bitmaps=0,closed=0;globalThis.createImageBitmap=async()=>{bitmaps++;return {close:()=>closed++};};
class WorkerStub{
 static instances=[];static ready=true;
 constructor(){this.sent=[];this.terminated=false;WorkerStub.instances.push(this);}
 postMessage(data){this.sent.push(data);if(data.type==="init"&&WorkerStub.ready)queueMicrotask(()=>this.onmessage({data:{type:"ready"}}));}
 terminate(){this.terminated=true;}
}
globalThis.Worker=WorkerStub;
function stream(){const track={stopped:false,stop(){this.stopped=true;}};return {track,getTracks:()=>[track],getVideoTracks:()=>[track]};}
let acquired=stream(),constraints;
Object.defineProperty(globalThis,"navigator",{value:{mediaDevices:{getUserMedia:async options=>(constraints=options,acquired)}},configurable:true});
function camera(){return new HandCamera({api:async()=>({ready:true}),onAction(){},onStatus(){},video:{srcObject:null,currentTime:1,play:async()=>{}},overlay:{width:480,height:360,getContext:()=>({clearRect(){}})}});}
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
let c=camera();await c.start();assert.equal(constraints.audio,false);assert(c.active);assert.equal(c.video.srcObject,acquired);
const worker=c.worker;frames.at(-1)(1000);await settle();assert.equal(worker.sent.filter(m=>m.type==="frame").length,1);
c.video.currentTime=2;frames.at(-1)(1200);await settle();assert.equal(worker.sent.filter(m=>m.type==="frame").length,1,"Only one inference frame may be in flight");
c.stop();assert(acquired.track.stopped);assert(worker.terminated);assert.equal(c.stream,null);assert.equal(c.video.srcObject,null);assert.equal(c.worker,null);
// A late permission response must close its own stream and must not resurrect a stopped session.
let resolve;acquired=stream();navigator.mediaDevices.getUserMedia=()=>new Promise(done=>resolve=done);
c=camera();const pending=c.start();await settle();c.stop();resolve(acquired);await pending;assert(acquired.track.stopped);assert(!c.active);
// Stop while WASM is loading must settle startup and free the stream and worker.
WorkerStub.ready=false;acquired=stream();navigator.mediaDevices.getUserMedia=async()=>acquired;
c=camera();const initializing=c.start();await settle();assert(c.worker);c.stop();await initializing;assert(acquired.track.stopped);assert(!c.worker);
// Camera unplug and hidden primary stop capture rather than keeping background frames running.
WorkerStub.ready=true;acquired=stream();c=camera();await c.start();acquired.track.onended();assert(!c.active);assert(acquired.track.stopped);
acquired=stream();c=camera();await c.start();document.hidden=true;listeners.visibilitychange();assert(!c.active);assert(acquired.track.stopped);document.hidden=false;
console.log("Camera has no audio, one in-flight frame, late permission cleanup, cancellable initialization, unplug and hidden-window stop.");