import {sampleTrack} from "./animation.js";
/* One bounded point cloud; worker jobs coalesce and GPU buffers are reused. */
export function createCenter(THREE,scene){
 const capacity=24000,geometry=new THREE.BufferGeometry();
 for(const [name,size] of [["position",3],["aFrom",3],["color",3],["aCenter",3],["aMotion",2],["aSeed",1],["aNode",1]])geometry.setAttribute(name,new THREE.BufferAttribute(new Float32Array(capacity*size),size).setUsage(THREE.DynamicDrawUsage));
 geometry.setDrawRange(0,0);
 const uniforms={uTime:{value:0},uMorph:{value:0},uOpacity:{value:0},uExplode:{value:0},uMode:{value:1},uSpeed:{value:1},uDpr:{value:1},uViewport:{value:new THREE.Vector4(0,0,1,1)},uNode:{value:Array.from({length:32},()=>new THREE.Matrix4())}};
 const material=new THREE.ShaderMaterial({uniforms,vertexColors:true,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,
 vertexShader:`attribute float aNode;uniform mat4 uNode[32];attribute vec3 aFrom;attribute vec3 aCenter;attribute vec2 aMotion;attribute float aSeed;varying vec3 vColor;varying float vAlpha;uniform float uTime,uMorph,uExplode,uMode,uSpeed,uDpr,uOpacity;
 mat3 ry(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
 void main(){vec3 p=position;float t=uTime*uSpeed;
 if(aMotion.x>.5&&aMotion.x<1.5)p=aCenter+ry(t*.8)*(p-aCenter);
 if(aMotion.x>1.5&&aMotion.x<2.5)p=ry(t*aMotion.y)*p;
 if(aMotion.x>2.5&&aMotion.x<3.5)p.y+=sin(t*1.3+aSeed*6.28)*.12;
 if(aMotion.x>3.5&&aMotion.x<4.5){float side=abs(aCenter.x)>.01?sign(aCenter.x):sign(position.x+.001);p=aCenter+ry(side*sin(t*3.)*.7)*(p-aCenter);}
 if(aMotion.x>4.5&&aMotion.x<5.5)p.y-=fract(t*.7+aSeed)*.8;
 if(aMotion.x>5.5)p=aCenter+(p-aCenter)*(1.+.10*sin(t*2.));
 p=(uNode[int(aNode)]*vec4(p,1.)).xyz;
 if(uMode>.5&&uMode<1.5)p=ry(t*.22)*p;
 if(uMode>1.5&&uMode<2.5)p*=1.+.08*sin(t*1.8);
 if(uMode>2.5&&uMode<3.5)p.y+=sin(p.x*3.+p.z*2.-t*1.5)*.20;
 if(uMode>3.5&&uMode<4.5)p=ry(t*.4)*p;
 if(uMode>4.5)p.y+=.24*sin(t*.9);
 vec3 direction=normalize(position+vec3(.001));p+=direction*uExplode*(.65+aSeed*1.9);
 float a=aSeed*6.283+t*.055;vec3 orb=vec3(cos(a),sin(a)*.82,sin(a*3.+aSeed*20.)*.32)*(1.1+aSeed*.2);
 float m=smoothstep(aSeed*.12,.9+aSeed*.1,uMorph);p=mix(aFrom,p,m);
 vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;gl_PointSize=clamp((1.+aSeed*.8)*uDpr*6.8/-mv.z,.8,3.5);
 vColor=color;vAlpha=uOpacity*(.45+.5*aSeed);}`,
 fragmentShader:`varying vec3 vColor;varying float vAlpha;uniform vec4 uViewport;void main(){if(gl_FragCoord.x<uViewport.x||gl_FragCoord.y<uViewport.y||gl_FragCoord.x>uViewport.z||gl_FragCoord.y>uViewport.w)discard;float d=length(gl_PointCoord-.5)*2.;if(d>1.)discard;gl_FragColor=vec4(vColor*(1.+.5*exp(-d*d*25.)),exp(-d*d*4.)*vAlpha);}`});
 const points=new THREE.Points(geometry,material);points.frustumCulled=false;points.visible=false;scene.add(points);
 const worker=new Worker(new URL("./center_worker.js",import.meta.url),{type:"module"});let latest=0,inflight=false,pending=null,result=null,lastBuild=-1,budget=0,mix=0,buildStarted=0,hasShape=false,animationTime=0,sceneStamp=null,frame={center:[0,0,0],fit:1};const rotation=new THREE.Euler(),quaternion=new THREE.Quaternion(),move=new THREE.Vector3(),stretch=new THREE.Vector3(),unpivot=new THREE.Matrix4();
 function drain(){if(inflight||!pending)return;inflight=true;worker.postMessage(pending);pending=null;}
 worker.onmessage=event=>{inflight=false;if(event.data.id===latest)result=event.data;drain();};worker.onerror=()=>{result={id:latest,error:"粒子模型后台构建失败"};inflight=false;};
 return {update(state,time,dt,metrics,suppressed=false){
  const center=state.center||{},limit=state.cityParticleBudget===16000?12000:20000;
  if(center.active&&center.plan&&(center.build!==lastBuild||budget!==limit)){lastBuild=center.build;budget=limit;pending={id:++latest,plan:center.plan,budget:limit};result=null;metrics.centerError=null;drain();metrics.centerLoading=true;}
  if(result?.data){
   const data=result.data;frame=data.frame||frame;result=null;const stamp=center.scene_id??center.build;if(stamp!==sceneStamp){animationTime=0;sceneStamp=stamp;}
   const from=geometry.attributes.aFrom.array,previous=geometry.attributes.position.array;
   if(hasShape)from.set(previous);else for(let i=0;i<data.count;i++){const a=data.seeds[i]*Math.PI*2;from[i*3]=Math.cos(a)*1.2;from[i*3+1]=Math.sin(a)*.95;from[i*3+2]=Math.sin(a*3.)*.3;}
   geometry.attributes.aFrom.needsUpdate=true;
   for(const [name,value]of [["position",data.positions],["color",data.colors],["aCenter",data.centers],["aMotion",data.motion],["aSeed",data.seeds],["aNode",data.nodes]]){geometry.attributes[name].array.set(value);geometry.attributes[name].needsUpdate=true;}
   geometry.setDrawRange(0,data.count);buildStarted=time;hasShape=true;metrics.centerParticles=data.count;metrics.centerLoading=false;metrics.centerError=null;
  }
  if(result?.error){metrics.centerError=result.error;metrics.centerLoading=false;}
  const target=center.active&&hasShape&&!suppressed?1:0;mix=Math.max(0,Math.min(1,mix+Math.sign(target-mix)*dt/1.4));
  points.visible=mix>.001;uniforms.uMorph.value=Math.min(mix,Math.max(0,Math.min(1,(time-buildStarted)/1.5)));uniforms.uOpacity.value=mix;
  if(!center.plan?.paused&&mix>.999&&time-buildStarted>=1.5)animationTime+=dt;uniforms.uTime.value=animationTime;uniforms.uDpr.value=metrics.pixelRatio||1;uniforms.uExplode.value+=(Number(center.explode||0)-uniforms.uExplode.value)*Math.min(1,dt*3);
  const plan=center.plan||{};uniforms.uMode.value=Math.max(0,["none","rotate","pulse","wave","orbit","fly"].indexOf(plan.motion));uniforms.uSpeed.value=plan.speed||1;
  for(let i=0;i<32;i++){
   const node=plan.nodes?.[i],matrix=uniforms.uNode.value[i];matrix.identity();if(!node?.frames)continue;
   const track=sampleTrack(node,animationTime*(plan.speed||1)),pivot=(node.pivot||node.position||[0,0,0]).map((v,k)=>(v-frame.center[k])*frame.fit);
   move.set(...track.move.map((v,k)=>v*frame.fit+pivot[k]));stretch.set(...track.stretch);rotation.set(...track.turn);quaternion.setFromEuler(rotation);
   matrix.compose(move,quaternion,stretch).multiply(unpivot.makeTranslation(-pivot[0],-pivot[1],-pivot[2]));
  }
  const tilt=plan.nodes?.some(n=>n.motion==="orbit"||["galaxy","wave"].includes(n.shape))?.72:.15;points.rotation.set(state.centerPitch??tilt,state.centerYaw||0,0);points.scale.setScalar(state.centerZoom||1);
  const dpr=metrics.pixelRatio||1,h=innerHeight,left=document.querySelector(".left-rail")?.getBoundingClientRect().right||0,right=document.querySelector(".right-rail")?.getBoundingClientRect().left||innerWidth;
  uniforms.uViewport.value.set((left+8)*dpr,h*.22*dpr,(right-8)*dpr,h*.80*dpr);
  metrics.centerMorph=Number(uniforms.uMorph.value.toFixed(3));metrics.centerPaused=!!plan.paused;metrics.centerAnimationTime=Number(animationTime.toFixed(3));
  metrics.centerMix=Number(mix.toFixed(3));metrics.centerBuild=lastBuild;metrics.centerTitle=plan.title||"";return mix;
 },close(){worker.terminate();geometry.dispose();material.dispose();scene.remove(points);}};
}
