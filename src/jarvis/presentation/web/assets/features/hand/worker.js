/* Local worker. Prefer GPU, retry CPU when this machine cannot create its GPU context. */
self.exports={};let detector=null,backend="CPU",vision,options;
self.onmessage=async event=>{
 const data=event.data;
 try{
  if(data.type==="init"){
   importScripts("/runtime/hand/vision_bundle.cjs");
   const {HandLandmarker,FilesetResolver}=self.exports;vision=await FilesetResolver.forVisionTasks("/runtime/hand/wasm");
   options={baseOptions:{modelAssetPath:"/runtime/hand/hand_landmarker.task",delegate:"GPU"},canvas:new OffscreenCanvas(640,480),
    runningMode:"VIDEO",numHands:2,minHandDetectionConfidence:.55,minHandPresenceConfidence:.55,minTrackingConfidence:.55};
   const warm=new OffscreenCanvas(256,192);warm.getContext("2d").fillRect(0,0,256,192);
   let coldMs=0,warmMs=0;
   async function prepare(delegate){
    detector=await HandLandmarker.createFromOptions(vision,{...options,baseOptions:{...options.baseOptions,delegate},canvas:delegate==="GPU"?options.canvas:undefined});backend=delegate;
    // Compile kernels during loading, before the camera frame response timeout.
    const started=performance.now();detector.detectForVideo(warm,0);coldMs=performance.now()-started;
    const costs=[];for(let i=1;i<=3;i++){const t=performance.now();detector.detectForVideo(warm,i);costs.push(performance.now()-t);}
    warmMs=costs.reduce((a,b)=>a+b,0)/costs.length;
   }
   try{await prepare("GPU");}catch(error){detector?.close();await prepare("CPU");}
   self.postMessage({type:"ready",backend,coldMs,warmMs});
  }else if(data.type==="frame"){
   const started=performance.now();
   try{
    if(!detector)throw new Error("识别器尚未就绪");
    const result=detector.detectForVideo(data.bitmap,data.timestamp);
    const milliseconds=performance.now()-started;
    self.postMessage({type:"result",landmarks:result.landmarks||[],worldLandmarks:result.worldLandmarks||[],timestamp:data.timestamp,backend,milliseconds});
   }finally{data.bitmap.close();}
  }else if(data.type==="close"){detector?.close();detector=null;self.close();}
 }catch(error){self.postMessage({type:"error",message:String(error.message||error)});}
};
