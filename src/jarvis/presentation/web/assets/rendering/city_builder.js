/* One CPU job in flight, only the latest pending viewport survives. */
export class CityBuilder{
 constructor(createWorker=()=>new Worker(new URL("./city_worker.js",import.meta.url),{type:"module"})){
  this.worker=createWorker();this.next=0;this.latest=0;this.inflight=false;this.pending=null;this.result=null;this.error=null;
  this.worker.onmessage=event=>{
   const value=event.data;this.inflight=false;
   if(value.id===this.latest){this.result=value;this.error=value.error||null;}
   this.drain();
  };
  this.worker.onerror=()=>{this.error="地图几何后台计算失败，请重新打开地图。";this.inflight=false;};
 }
 request(scene,budget,revision){
  const id=++this.next;this.latest=id;this.pending={id,data:scene.context||{},path:scene.path||[],view:scene.view||"start",focus:scene.focus||null,options:{extent:scene.extent,heightScale:16,particleBudget:budget},revision};
  this.drain();return id;
 }
 drain(){if(this.inflight||!this.pending)return;this.inflight=true;const task=this.pending;this.pending=null;this.worker.postMessage(task);}
 close(){this.worker.terminate();this.pending=null;this.result=null;}
}
