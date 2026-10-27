import {createParticleCity} from "./city.js";
import * as THREE from "./vendor/three.module.js";
const ribbonGLSL=`
uniform float uTime; uniform float uPhase; uniform float uLevel; uniform float uMapMix;
const float PI=3.14159265359;
mat3 rotX(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
mat3 rotY(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
mat3 rotZ(float a){float c=cos(a),s=sin(a);return mat3(c,s,0.,-s,c,0.,0.,0.,1.);}
vec3 ribbon(float t,float lane,float seed){
 float speed=uTime*.13,s=seed*1.618;
 float width=.17+.055*sin(t*2.+s+uTime*.31)+uPhase*.048;
 float radius=1.16+.20*sin(t*3.+s+uTime*.17)+lane*width;
 radius+=uPhase*.075*sin(t*5.-uTime*.35+s)+uLevel*.075*sin(t*4.+s);
 float a=t+.19*sin(t*2.+s+uTime*.08);
 vec3 p=vec3(radius*cos(a),radius*sin(a)*(.79+.05*sin(s)),.38*sin(t*2.+s+uTime*.20)+lane*.065*cos(t*3.+s));
 p=rotX(.48+seed*.48+uPhase*.18*sin(s))*rotZ(seed*1.09+speed*.26)*p;
 p=rotY(speed*.42+sin(uTime*.09)*.2)*p;
 p.y+=.04*sin(uTime*.6+s);
 // Unfurl the curved energy ribbons into a thin, wide plane before dissolving.
 vec3 plane=vec3((t/PI-1.)*2.25,lane*.40+sin(t*2.+s)*.38,0.);
 return mix(p,plane,smoothstep(0.,1.,uMapMix));

}
`;
const meshVertex=ribbonGLSL+`
uniform float uSeed; varying vec2 vUv; varying vec3 vWorld;
void main(){vUv=uv;vec3 p=ribbon(uv.x*PI*2.,(uv.y-.5)*2.,uSeed);
 vec4 world=modelMatrix*vec4(p,1.);vWorld=world.xyz;gl_Position=projectionMatrix*viewMatrix*world;}
`;
const meshFragment=`
uniform float uTime;uniform float uSeed;uniform float uPhase;uniform float uMapMix;
varying vec2 vUv;varying vec3 vWorld;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
void main(){
 vec3 normal=normalize(cross(dFdx(vWorld),dFdy(vWorld)));
 vec3 viewDir=normalize(cameraPosition-vWorld);
 float fresnel=pow(1.-abs(dot(normal,viewDir)),1.6);
 float edge=pow(max(sin(vUv.y*3.14159265),0.),.6);
 float strandWave=vUv.y*24.+sin(vUv.x*31.-uTime*.24+uSeed)*.15;
 float lineDist=abs(fract(strandWave)-.5);
 float footprint=fwidth(strandWave);
 float aa=min(.10,footprint*.55);
 float resolved=1.-smoothstep(.09-aa,.09+aa,lineDist);
 float fibers=mix(resolved,.18,smoothstep(.28,.65,footprint));
 float fine=.5+.5*sin(vUv.x*760.+vUv.y*210.+uTime*.7);
 float grain=hash(floor(vUv*vec2(1600.,120.)));
 float flow=.65+.35*sin(vUv.x*20.-uTime*.45+uSeed*2.);
 vec3 ice=vec3(.20,.65,1.),pearl=vec3(.80,.94,1.),warm=vec3(1.,.72,.57);
 float tint=.5+.5*sin(uSeed*2.1+vUv.x*4.);
 vec3 color=mix(ice,pearl,.34+.35*tint);
 if(uSeed>3.4)color=mix(color,warm,.40+.25*sin(vUv.x*6.+uSeed));
 color=mix(color,vec3(.65,.68,1.),uPhase*.12);
 float intensity=.65+fibers*1.1+fine*.02+fresnel*.45+grain*.06;
 float alpha=edge*(.065+fibers*.10+fresnel*.070)*flow;
 gl_FragColor=vec4(color*intensity*1.5,alpha*(1.-uMapMix));
}
`;
const pointsVertex=ribbonGLSL+`
attribute vec4 aSeed;uniform float uMode;uniform float uDpr;
varying vec3 vColor;varying float vAlpha;
void main(){
 vec3 p=position;float size=.72+aSeed.w*1.15;
 if(uMode>.5 && uMode<1.5){
  float a=aSeed.x*PI*2.+uTime*(.035+aSeed.w*.012);
  float radius=.25+pow(aSeed.y,.57)*1.65;
  p=vec3(cos(a)*radius,sin(a)*radius*.79,(aSeed.z-.5)*1.14);
  p=rotY(uTime*.05)*rotX(.43)*p;
  p+=vec3(sin(a*3.+uTime*.18),cos(a*2.+uTime*.14),sin(a*4.))*uPhase*.08;
  p*=1.+uPhase*.07+uLevel*.035;size*=.72;
 }else if(uMode>1.5 && uMode<2.5){
  p=ribbon(aSeed.x*PI*2.+uTime*(.035+uPhase*.024),(aSeed.y-.5)*2.05,floor(aSeed.z*6.));
  size*=.85;
 }else if(uMode>2.5){
  p.y=mod(position.y-uTime*(.035+aSeed.w*.025)+2.8,5.6)-2.8;size*=.65;
 }
 if(uMode>.5 && uMode<2.5){
  vec3 plane=vec3((aSeed.x-.5)*4.5,(aSeed.y-.5)*2.,0.);
  p=mix(p,plane,smoothstep(0.,1.,uMapMix));
 }
 vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;
 gl_PointSize=clamp(size*uDpr*(7.0/-mv.z),.65,4.5);
 vColor=mix(vec3(.38,.68,1.),vec3(.92,.97,1.),aSeed.w);
 if(aSeed.z>.85 && uMode>1.5)vColor=mix(vColor,vec3(1.,.66,.45),.48);
 vAlpha=(.16+pow(aSeed.y,2.)*.65)*(.78+.22*sin(uTime*.6+aSeed.x*40.));
 if(uMode<.5)vAlpha*=.66;else if(uMode<2.5)vAlpha*=1.-uMapMix;
}
`;
const pointsFragment=`
varying vec3 vColor;varying float vAlpha;
void main(){
 float r=length(gl_PointCoord-.5)*2.;
 float soft=exp(-r*r*4.2)*(1.-smoothstep(.65,1.,r));
 float center=exp(-r*r*29.);
 gl_FragColor=vec4(vColor*(1.1+center*1.6),soft*vAlpha);
}
`;
const screenVertex=`
varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}
`;
const thresholdFragment=`
uniform sampler2D uSource;varying vec2 vUv;
void main(){
 vec3 color=texture2D(uSource,vUv).rgb;
 float bright=max(max(color.r,color.g),color.b);
 gl_FragColor=vec4(color*smoothstep(.48,1.12,bright),1.);
}
`;
const blurFragment=`
uniform sampler2D uSource;uniform vec2 uDirection;varying vec2 vUv;
void main(){
 vec3 c=texture2D(uSource,vUv).rgb*.227027;
 c+=texture2D(uSource,vUv+uDirection*1.384615).rgb*.316216;
 c+=texture2D(uSource,vUv-uDirection*1.384615).rgb*.316216;
 c+=texture2D(uSource,vUv+uDirection*3.230769).rgb*.070270;
 c+=texture2D(uSource,vUv-uDirection*3.230769).rgb*.070270;
 gl_FragColor=vec4(c,1.);
}
`;
const combineFragment=`
uniform sampler2D uScene;uniform sampler2D uBloom;uniform float uExposure;uniform float uBloomGain;varying vec2 vUv;
vec3 aces(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.);}
vec3 srgb(vec3 c){return mix(c*12.92,1.055*pow(max(c,vec3(0.)),vec3(1./2.4))-.055,step(vec3(.0031308),c));}
void main(){
 vec3 original=texture2D(uScene,vUv).rgb,bloom=texture2D(uBloom,vUv).rgb;
 vec3 c=aces((original+bloom*uBloomGain)*uExposure);
 float vignette=1.-.16*pow(length((vUv-.5)*vec2(1.1,1.)),1.8);
 gl_FragColor=vec4(srgb(c)*vignette,1.);
}
`;

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
 const particleCity=createParticleCity(THREE,scene,camera);
 const uniforms={uTime:{value:0},uPhase:{value:0},uLevel:{value:0},uDpr:{value:1},uMapMix:{value:0}};
 const ribbons=new THREE.Group();scene.add(ribbons);const geometry=makeRibbonGeometry();
 for(let i=0;i<6;i++){
  const material=new THREE.ShaderMaterial({uniforms:{...uniforms,uSeed:{value:i}},vertexShader:meshVertex,
   fragmentShader:meshFragment,side:THREE.DoubleSide,transparent:true,depthWrite:false,
   blending:THREE.AdditiveBlending,toneMapped:false});
  const mesh=new THREE.Mesh(geometry,material);mesh.frustumCulled=false;ribbons.add(mesh);
 }
 const layers=[makePoints(3600,0,uniforms),makePoints(10500,1,uniforms),makePoints(3600,2,uniforms),makePoints(600,3,uniforms)];
 for(const layer of layers)scene.add(layer);
 const threads=[];
 for(let i=0;i<125;i++){
  const x=Math.sin(i*117.13)*2.2,z=Math.cos(i*41.7)*.9,y=Math.sin(i*17.9)*2.1;
  threads.push(x,y,z,x,y+.12+(i%7)*.055,z);
 }
 const threadG=new THREE.BufferGeometry();threadG.setAttribute("position",new THREE.Float32BufferAttribute(threads,3));
 const threadM=new THREE.LineBasicMaterial({color:0x5594b7,transparent:true,opacity:.060,
  depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
 scene.add(new THREE.LineSegments(threadG,threadM));
 const orbits=[];
 for(let k=0;k<4;k++){
  const pts=[];
  for(let i=0;i<=240;i++){const a=i/240*Math.PI*2;pts.push(new THREE.Vector3(Math.cos(a)*(1.69+k*.025),Math.sin(a)*(.58+k*.11),0));}
  const g=new THREE.BufferGeometry().setFromPoints(pts);
  const m=new THREE.LineBasicMaterial({color:k===3?0xf1b38f:0x89c5df,transparent:true,opacity:k===3?.16:.20,
   depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
  const orbit=new THREE.Line(g,m);orbit.rotation.set(.24+k*.36,k*.28,k*.39);scene.add(orbit);orbits.push(orbit);
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
 function draw(stamp){
  if(!running)return;requestAnimationFrame(draw);
  if(document.hidden){last=stamp;previous=stamp;return;}
  const activeBudget=state.mapReady?Math.max(budget,1000/24):budget;
  const delta=stamp-last;if(delta<activeBudget-1)return;last=stamp-(delta%activeBudget);
  const begin=performance.now(),dt=Math.min((stamp-previous)/1000,.1);previous=stamp;elapsed+=dt;
  phase+=(Number(state.phase==="dialogue")-phase)*Math.min(1,dt*2.2);level+=(Number(state.level||0)-level)*Math.min(1,dt*8);
  // A time-based, reversible flight lasts 2.6 seconds; city particles travel, rather than crossfade.
  const target=Number(!!state.mapReady);
  mapMix=THREE.MathUtils.clamp(mapMix+Math.sign(target-mapMix)*dt/2.6,0,1);
  uniforms.uMapMix.value=THREE.MathUtils.smoothstep(mapMix,0,.48);metrics.mapMix=Number(mapMix.toFixed(3));
  metrics.morphDuration=2.6;metrics.morphDirection=mapMix===target?"stable":target?"city":"energy";
  particleCity.update(state,mapMix,elapsed,metrics);
  for(const orbit of orbits)orbit.visible=mapMix<.95;
  uniforms.uTime.value=elapsed;uniforms.uPhase.value=phase;uniforms.uLevel.value=level;ribbons.rotation.z=Math.sin(elapsed*.08)*.055;
  for(let i=0;i<orbits.length;i++)orbits[i].rotation.z+=dt*(i%2?.016:-.012);
  renderer.info.reset();renderer.setRenderTarget(sceneTarget);renderer.render(scene,camera);renderPost(threshold,ping);
  for(let iteration=0;iteration<2;iteration++){
   blur.uniforms.uSource.value=ping.texture;blur.uniforms.uDirection.value.set((1.1+iteration)/ping.width,0);renderPost(blur,pong);
   blur.uniforms.uSource.value=pong.texture;blur.uniforms.uDirection.value.set(0,(1.1+iteration)/ping.height);renderPost(blur,ping);
  }
  combine.uniforms.uBloomGain.value=.65*(1-THREE.MathUtils.smoothstep(mapMix,0,.45));
  combine.uniforms.uExposure.value=(1.15+phase*.04+level*.035)*(1-mapMix)+.95*mapMix;renderPost(combine,null);
  const cost=performance.now()-begin;
  metrics.frames=(metrics.frames||0)+1;metrics.meanMs=(metrics.meanMs||cost)*.95+cost*.05;
  metrics.triangles=renderer.info.render.triangles;metrics.phase=state.phase;metrics.ready=!window.__renderError;metrics.drawCalls=renderer.info.render.calls;frames++;
  if(stamp-fpsStart>=1200){metrics.fps=Math.round(frames*1000/(stamp-fpsStart));frames=0;fpsStart=stamp;}
  if(delta>70)slow++;else slow=Math.max(0,slow-1);
  if(slow>30 && dpr>1){dpr=1;resize();slow=0;}
 }
 resize();addEventListener("resize",resize);requestAnimationFrame(draw);
 canvas.addEventListener("webglcontextlost",event=>{event.preventDefault();metrics.ready=false;window.__renderError="WebGL context lost";});
 return {setLowQuality(low){budget=1000/(low?20:30);dpr=low?1:Math.min(devicePixelRatio||1,1.25);resize();},
  stop(){running=false;removeEventListener("resize",resize);renderer.dispose();sceneTarget.dispose();ping.dispose();pong.dispose();}};
}