/* Classic worker: Emscripten uses importScripts for its local WASM loader. */
self.exports={};
let detector=null;
self.onmessage=async event=>{
 const data=event.data;
 try{
  if(data.type==="init"){
   importScripts("/runtime/hand/vision_bundle.cjs");
   const {HandLandmarker,FilesetResolver}=self.exports;
   const vision=await FilesetResolver.forVisionTasks("/runtime/hand/wasm");
   detector=await HandLandmarker.createFromOptions(vision,{baseOptions:{modelAssetPath:"/runtime/hand/hand_landmarker.task",delegate:"CPU"},
    runningMode:"VIDEO",numHands:2,minHandDetectionConfidence:.65,minHandPresenceConfidence:.65,minTrackingConfidence:.65});
   self.postMessage({type:"ready"});
  }else if(data.type==="frame"){
   const started=performance.now();
   try{
    if(!detector)throw new Error("识别器尚未就绪");
    const result=detector.detectForVideo(data.bitmap,data.timestamp);
    self.postMessage({type:"result",landmarks:result.landmarks||[],milliseconds:performance.now()-started});
   }finally{data.bitmap.close();}
  }else if(data.type==="close"){detector?.close();detector=null;self.close();}
 }catch(error){self.postMessage({type:"error",message:String(error.message||error)});}
};
