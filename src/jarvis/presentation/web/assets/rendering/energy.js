import {createCenter} from "./center.js";
import {visualActivity} from "./activity.js";
import {createAssembly} from "./assembly.js";
import {transferFrame} from "./transfer.js";
import {createParticleCity} from "./city.js";
import * as THREE from "../vendor/three.module.js";
import {ribbonGLSL,meshVertex,meshFragment,pointsVertex,pointsFragment,screenVertex,thresholdFragment,blurFragment,combineFragment} from "./shaders.js";
function makeRibbonGeometry(){
 const length=300,width=14,positions=[],uvs=[],indices=[];
 for(let j=0;j<=length;j++)for(let k=0;k<=width;k++){positions.push(j/length,k/width,0);uvs.push(j/length,k/width);}
 for(let j=0;j<length;j++)for(let k=0;k<width;k++){let a=j*(width+1)+k,b=a+width+1;indices.push(a,b,a+1,b,b+1,a+1);}
 const g=new THREE.BufferGeometry();
 g.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));
 g.setAttribute("uv",new THREE.Float32BufferAttribute(uvs,2));g.setIndex(indices);return g;
}
function makePoints(count,mode,uniforms){
 const positions=new Float32Array(count*3),seeds=new Float32Array(count*4);
 let seed=12345+mode*7701;const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 for(let i=0;i<count;i++){
  if(mode===0){positions[i*3]=(rand()-.5)*22;positions[i*3+1]=(rand()-.5)*13;positions[i*3+2]=-3-rand()*7;}
  if(mode===3){positions[i*3]=(rand()-.5)*4.9;positions[i*3+1]=(rand()-.5)*5.3;positions[i*3+2]=(rand()-.5)*1.8;}
  for(let k=0;k<4;k++)seeds[i*4+k]=rand();
 }
 const geometry=new THREE.BufferGeometry();geometry.setAttribute("position",new THREE.BufferAttribute(positions,3));
 geometry.setAttribute("aSeed",new THREE.BufferAttribute(seeds,4));
 const material=new THREE.ShaderMaterial({uniforms:{...uniforms,uMode:{value:mode}},vertexShader:pointsVertex,
  fragmentShader:pointsFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
 const points=new THREE.Points(geometry,material);points.frustumCulled=false;return points;
}
export function createVisual(canvas,state,metrics){
 const renderer=new THREE.WebGLRenderer({canvas,antialias:false,alpha:false,powerPreference:"high-performance"});
 const gl=renderer.getContext();
 renderer.info.autoReset=false;renderer.outputColorSpace=THREE.LinearSRGBColorSpace;renderer.toneMapping=THREE.NoToneMapping;renderer.setClearColor(0x030710,1);
 renderer.debug.onShaderError=(context,program,vertex,fragment)=>{
  window.__renderError=[context.getProgramInfoLog(program),context.getShaderInfoLog(vertex),context.getShaderInfoLog(fragment)].join("\n");
 };
 const debug=gl.getExtension("WEBGL_debug_renderer_info");
 metrics.renderer=debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
 metrics.engine="Three.js r"+THREE.REVISION+" / WebGL2";metrics.particles=18300;
 const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.1,60);
 camera.position.set(0,.05,6.8);camera.lookAt(0,0,0);
 const particleCity=createParticleCity(THREE,scene,camera),assembly=createAssembly(THREE),center=state.mapOnly?{update:()=>0,close(){}}:createCenter(THREE,scene);
 const uniforms={uTime:{value:0},uPhase:{value:0},uLevel:{value:0},uDpr:{value:1},uMapMix:{value:0},uActivity:{value:0},uCoreFade:{value:1}};
 const energy=new THREE.Group();scene.add(energy);
 const ribbons=new THREE.Group();energy.add(ribbons);const geometry=makeRibbonGeometry();
 for(let i=0;i<6;i++){
  const material=new THREE.ShaderMaterial({uniforms:{...uniforms,uSeed:{value:i}},vertexShader:meshVertex,
   fragmentShader:meshFragment,side:THREE.DoubleSide,transparent:true,depthWrite:false,
   blending:THREE.AdditiveBlending,toneMapped:false});
  const mesh=new THREE.Mesh(geometry,material);mesh.frustumCulled=false;ribbons.add(mesh);
 }
 const layers=[makePoints(3600,0,uniforms),makePoints(10500,1,uniforms),makePoints(3600,2,uniforms),makePoints(600,3,uniforms)];
 for(let i=0;i<layers.length;i++)(i===1||i===2?energy:scene).add(layers[i]);
 const threads=[];
 for(let i=0;i<125;i++){
  const x=Math.sin(i*117.13)*2.2,z=Math.cos(i*41.7)*.9,y=Math.sin(i*17.9)*2.1;
  threads.push(x,y,z,x,y+.12+(i%7)*.055,z);
 }
 const threadG=new THREE.BufferGeometry();threadG.setAttribute("position",new THREE.Float32BufferAttribute(threads,3));
 const threadM=new THREE.LineBasicMaterial({color:0x6654a6,transparent:true,opacity:.060,
  depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
 scene.add(new THREE.LineSegments(threadG,threadM));
 const orbits=[];
 for(let k=0;k<4;k++){
  const pts=[];
  for(let i=0;i<=240;i++){const a=i/240*Math.PI*2;pts.push(new THREE.Vector3(Math.cos(a)*(1.69+k*.025),Math.sin(a)*(.58+k*.11),0));}
  const g=new THREE.BufferGeometry().setFromPoints(pts);
  const m=new THREE.LineBasicMaterial({color:k===3?0xeaa5d9:0xb2a9ef,transparent:true,opacity:k===3?.16:.20,
   depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
  const orbit=new THREE.Line(g,m);orbit.rotation.set(.24+k*.36,k*.28,k*.39);energy.add(orbit);orbits.push(orbit);
 }
 const targetType=gl.getExtension("EXT_color_buffer_float")?THREE.HalfFloatType:THREE.UnsignedByteType;
 metrics.hdr=targetType===THREE.HalfFloatType;
 const sceneTarget=new THREE.WebGLRenderTarget(1,1,{type:targetType,depthBuffer:true,minFilter:THREE.LinearFilter,magFilter:THREE.LinearFilter});
 const ping=new THREE.WebGLRenderTarget(1,1,{type:targetType,depthBuffer:false}),pong=ping.clone();
 const postScene=new THREE.Scene(),postCamera=new THREE.Camera(),quad=new THREE.Mesh(new THREE.PlaneGeometry(2,2));postScene.add(quad);
 const threshold=new THREE.ShaderMaterial({uniforms:{uSource:{value:sceneTarget.texture}},vertexShader:screenVertex,fragmentShader:thresholdFragment,depthTest:false,depthWrite:false,toneMapped:false});
 const blur=new THREE.ShaderMaterial({uniforms:{uSource:{value:null},uDirection:{value:new THREE.Vector2()}},vertexShader:screenVertex,fragmentShader:blurFragment,depthTest:false,depthWrite:false,toneMapped:false});
 const combine=new THREE.ShaderMaterial({uniforms:{uScene:{value:sceneTarget.texture},uBloom:{value:ping.texture},uExposure:{value:1.18},uBloomGain:{value:.65}},vertexShader:screenVertex,fragmentShader:combineFragment,depthTest:false,depthWrite:false,toneMapped:false});
 let width=1,height=1,dpr=Math.min(devicePixelRatio||1,1.25),budget=1000/30;
 let elapsed=0,last=0,frames=0,fpsStart=performance.now(),previous=performance.now(),running=true,slow=0,phase=0,level=0,mapMix=0;
 function resize(){
  width=canvas.clientWidth||innerWidth;height=canvas.clientHeight||innerHeight;
  renderer.setPixelRatio(dpr);renderer.setSize(width,height,false);uniforms.uDpr.value=dpr;
  camera.aspect=width/height;camera.updateProjectionMatrix();camera.position.z=width<850?7.6:6.8;
  const size=renderer.getDrawingBufferSize(new THREE.Vector2());
  sceneTarget.setSize(size.x,size.y);ping.setSize(Math.max(1,size.x>>1),Math.max(1,size.y>>1));pong.setSize(ping.width,ping.height);
  metrics.resolution=[size.x,size.y];metrics.pixelRatio=dpr;
 }
 function renderPost(material,target){quad.material=material;renderer.setRenderTarget(target);renderer.render(postScene,postCamera);}
 let frameRequest=null,hiddenTimer=null;
 function schedule(){if(state.forceRender&&(document.hidden||state.mapPreparing))hiddenTimer=setTimeout(()=>draw(performance.now()),50);else frameRequest=requestAnimationFrame(draw);}
 function draw(stamp){
  if(!running)return;schedule();
  if(document.hidden&&!state.forceRender){last=stamp;previous=stamp;return;}
  const activeBudget=state.mapReady&&!state.mapDetached?Math.max(budget,1000/24):budget;
  const delta=stamp-last;if(delta<activeBudget-1)return;last=stamp-(delta%activeBudget);
  const begin=performance.now(),dt=Math.min((stamp-previous)/1000,.1);previous=stamp;elapsed+=dt;
  phase+=(Number(state.phase==="dialogue")-phase)*Math.min(1,dt*2.2);level+=(Number(state.level||0)-level)*Math.min(1,dt*8);
  const transfer=transferFrame(state.mapTransfer,stamp);
  let renderState=state,cityMix;
  if(state.mapTransfer&&!transfer.active&&!state.mapTransfer.finished){
   state.mapTransfer.finished=true;mapMix=state.mapTransfer.phase==="depart"?0:1;
  }
  if(state.mapPreparing){mapMix=1;cityMix=1;}
  else if(transfer.active){
   mapMix=transfer.energyMix;cityMix=1;
   if(transfer.phase==="depart")renderState={...state,...state.mapTransfer.source,mapTransfer:state.mapTransfer};
  }else{
   const target=Number(!!state.mapReady);
   mapMix=THREE.MathUtils.clamp(mapMix+Math.sign(target-mapMix)*dt/2.6,0,1);cityMix=mapMix;
  }
  const centerMix=center.update(state,elapsed,dt,metrics,state.mapOnly||mapMix>.01||transfer.active);
  const activity=visualActivity(state);uniforms.uActivity.value+=(activity.code-uniforms.uActivity.value)*Math.min(1,dt*5);uniforms.uCoreFade.value=1-centerMix;
  metrics.visualActivity=activity.name;metrics.activityCode=Number(uniforms.uActivity.value.toFixed(2));metrics.palette="indigo-violet-rose-starlight";
  uniforms.uMapMix.value=THREE.MathUtils.smoothstep(mapMix,0,.48);metrics.mapMix=Number(mapMix.toFixed(3));
  metrics.transferPhase=transfer.active?transfer.phase:"idle";metrics.transferProgress=Number(transfer.progress.toFixed(3));
  metrics.transferDirection=transfer.direction;metrics.morphDuration=2.6;
  metrics.morphDirection=transfer.active?"transfer":mapMix===Number(!!state.mapReady)?"stable":state.mapReady?"city":"energy";
  if(!transfer.active&&!state.mapReady&&mapMix===0)particleCity.hide();
  else particleCity.update(renderState,cityMix,elapsed,metrics,transfer);
  for(const orbit of orbits)orbit.visible=!state.mapOnly&&mapMix<.95&&centerMix<.8;
  ribbons.visible=!state.mapOnly&&centerMix<.999;
  for(let i=1;i<layers.length;i++)layers[i].visible=!state.mapOnly&&centerMix<.999;
  // Idle motion uses the render clock, never voice level or task progress. Fade it
  // out before dedicated map/model forms so their coordinates remain stable.
  const idleWeight=Math.max(0,1-uniforms.uActivity.value)*(1-THREE.MathUtils.smoothstep(mapMix,0,.25))*(1-centerMix);
  const breath=1+.045*Math.sin(elapsed*Math.PI/2.6)*idleWeight;
  energy.scale.setScalar(breath);
  energy.rotation.set(Math.sin(elapsed*.27)*.065*idleWeight,Math.sin(elapsed*.13)*.75*idleWeight,Math.sin(elapsed*.22)*.09*idleWeight);
  metrics.energyTime=Number(elapsed.toFixed(3));metrics.idleBreath=Number(breath.toFixed(5));metrics.idleWeight=Number(idleWeight.toFixed(3));
  metrics.energyRotation=energy.rotation.toArray().slice(0,3);
  uniforms.uTime.value=elapsed;uniforms.uPhase.value=phase;uniforms.uLevel.value=level;ribbons.rotation.z=Math.sin(elapsed*.08)*.055;
  for(let i=0;i<orbits.length;i++)orbits[i].rotation.z+=dt*(i%2?.016:-.012);
  renderer.info.reset();renderer.setRenderTarget(sceneTarget);renderer.render(scene,camera);
  if(mapMix<.995){
   renderPost(threshold,ping);
   for(let iteration=0;iteration<2;iteration++){
   blur.uniforms.uSource.value=ping.texture;blur.uniforms.uDirection.value.set((1.1+iteration)/ping.width,0);renderPost(blur,pong);
   blur.uniforms.uSource.value=pong.texture;blur.uniforms.uDirection.value.set(0,(1.1+iteration)/ping.height);renderPost(blur,ping);
  }
  }
  metrics.postPasses=mapMix<.995?6:1;
  metrics.gpuGeometries=renderer.info.memory.geometries;metrics.gpuTextures=renderer.info.memory.textures;
  metrics.gpuPrograms=renderer.info.programs?.length||0;
  combine.uniforms.uBloomGain.value=.65*(1-THREE.MathUtils.smoothstep(mapMix,0,.45))*(1-centerMix*.78);
  combine.uniforms.uExposure.value=(1.15+phase*.04+level*.035)*(1-mapMix)+.95*mapMix;renderPost(combine,null);
  assembly.update(state,transfer,width,height,dpr,metrics);assembly.render(renderer);
  const cost=performance.now()-begin;
  metrics.frames=(metrics.frames||0)+1;metrics.meanMs=(metrics.meanMs||cost)*.95+cost*.05;
  metrics.triangles=renderer.info.render.triangles;metrics.phase=state.phase;metrics.ready=!window.__renderError;metrics.drawCalls=renderer.info.render.calls;frames++;
  if(stamp-fpsStart>=1200){metrics.fps=Math.round(frames*1000/(stamp-fpsStart));frames=0;fpsStart=stamp;}
  if(delta>70)slow++;else slow=Math.max(0,slow-1);
  if(slow>30 && dpr>1){dpr=1;resize();slow=0;}
 }
 resize();addEventListener("resize",resize);schedule();
 canvas.addEventListener("webglcontextlost",event=>{event.preventDefault();metrics.ready=false;window.__renderError="WebGL context lost";});
 return {setLowQuality(low){state.cityParticleBudget=low?16000:36000;budget=1000/(low?20:30);dpr=low?1:Math.min(devicePixelRatio||1,1.25);resize();},
  stop(){running=false;cancelAnimationFrame(frameRequest);clearTimeout(hiddenTimer);assembly.close();center.close();removeEventListener("resize",resize);particleCity.close();renderer.dispose();sceneTarget.dispose();ping.dispose();pong.dispose();}};
}