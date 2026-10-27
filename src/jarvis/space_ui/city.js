import {DEFAULT_EXTENT,DEFAULT_HEIGHT_SCALE,routeFrame} from "./map_controls.js";
/* Accurate source coordinates, polygon courtyards and independently exaggerated architecture. */
export function inside(point,ring){
 let yes=false;
 for(let i=0,j=ring.length-1;i<ring.length;j=i++){
  const a=ring[i],b=ring[j];
  if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes;
 }return yes;
}
export function clipSegment(a,b,bounds){
 const dx=b[0]-a[0],dy=b[1]-a[1],p=[-dx,dx,-dy,dy],q=[a[0]+bounds[0],bounds[0]-a[0],a[1]+bounds[1],bounds[1]-a[1]];
 let low=0,high=1;
 for(let i=0;i<4;i++){
  if(Math.abs(p[i])<1e-12){if(q[i]<0)return null;continue;}
  const t=q[i]/p[i];if(p[i]<0)low=Math.max(low,t);else high=Math.min(high,t);
  if(low>high)return null;
 }
 return [[a[0]+low*dx,a[1]+low*dy],[a[0]+high*dx,a[1]+high*dy]];
}
export function buildCityPositions(data,path,view="start",focus=null,options={}){
 const basis=path.length?path:(data.roads?.[0]?.path||data.buildings?.[0]?.footprint||[]);
 const empty={points:[],colors:[],fades:[],edges:[],streets:[],arterials:[],paths:[],route:[],routeParts:[],labels:[],origin:[0,0],scale:1,renderedBuildings:0};
 if(!basis.length)return empty;
 const overview=view==="overview",localExtent=Math.max(400,Math.min(5000000,Number(options.extent)||DEFAULT_EXTENT));
 const frame=routeFrame(basis,localExtent);
 const origin=overview?frame.origin:(focus||(view==="end"?basis.at(-1):basis[0]));
 const cos=Math.cos(origin[1]*Math.PI/180),meters=p=>[(p[0]-origin[0])*111320*cos,(p[1]-origin[1])*111320];
 const routeM=basis.map(meters),extent=overview?frame.extent:localExtent;
 const scale=3.9/extent,bounds=[2.4/scale,1.6/scale],heightScale=Math.max(1,Math.min(32,Number(options.heightScale)||DEFAULT_HEIGHT_SCALE));
 const particleBudget=Math.max(8000,Math.min(36000,Number(options.particleBudget)||36000));
 const points=[],colors=[],fades=[],edges=[],streets=[],arterials=[],paths=[],route=[],routeParts=[],labels=[];
 let quota=36000,used=0,visualMaxHeight=0;
 function put(x,y,z,color){
  if(points.length>=particleBudget*3||used>=quota||Math.abs(x)>bounds[0]||Math.abs(z)>bounds[1])return;
  const fade=Math.max(.05,1-Math.max(Math.abs(x)/bounds[0],Math.abs(z)/bounds[1])**8);
  points.push(x*scale,y*scale,-z*scale);colors.push(...color);fades.push(fade);used++;
 }
 function edge(a,b,height){
  const clipped=clipSegment(a,b,bounds);if(!clipped||edges.length>=360000)return;
  for(const p of clipped)edges.push(p[0]*scale,height*scale,-p[1]*scale);
 }
 function grains(a,b,height,color,spacing=4){
  const clipped=clipSegment(a,b,bounds);if(!clipped)return;
  [a,b]=clipped;const count=Math.min(240,Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/spacing)));
  for(let i=0;i<count;i++){const t=i/count;put(a[0]+(b[0]-a[0])*t,height,a[1]+(b[1]-a[1])*t,color);}
 }
 const buildings=(data.buildings||[]).map(building=>{
  const ring=building.footprint.map(meters),x=ring.map(p=>p[0]),z=ring.map(p=>p[1]);
  const distance=ring.reduce((s,p)=>s+Math.hypot(...p),0)/ring.length;
  return {building,ring,distance,xmin:Math.min(...x),xmax:Math.max(...x),zmin:Math.min(...z),zmax:Math.max(...z)};
 }).filter(b=>b.xmin<bounds[0]&&b.xmax>-bounds[0]&&b.zmin<bounds[1]&&b.zmax>-bounds[1]).sort((a,b)=>a.distance-b.distance);
 if(!overview){
  quota=Math.max(12,Math.floor(particleBudget/Math.max(1,buildings.length)));
  for(const item of buildings){
   used=0;
   const {building,ring}=item,holes=(building.holes||[]).map(h=>h.map(meters));
   const realHeight=Math.min(500,Math.max(3,Number(building.height)||12));
   // Keep very tall source towers on screen without modifying the source height.
   const h=Math.min(realHeight*heightScale,1.7/scale),bottom=Math.max(0,Number(building.min_height)||0)/realHeight*h;
   visualMaxHeight=Math.max(visualMaxHeight,h*scale);
   for(const wall of [ring,...holes])for(let i=1;i<wall.length;i++){
    const a=wall[i-1],b=wall[i];
    edge(a,b,h);edge(a,b,bottom);grains(a,b,h,[.55,.73,.80]);
    const clipped=clipSegment(a,b,bounds);if(!clipped)continue;
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]),count=Math.max(1,Math.min(20,Math.ceil(length/6)));
    const shade=.45+.35*Math.abs((b[0]-a[0])/(length||1));
    for(let j=0;j<=count&&used<quota;j++){
     const t=j/count,x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;
     for(let y=bottom;y<h&&used<quota;y+=Math.max(8,(h-bottom)/10))put(x,y,z,[.22*shade,.40*shade,.52*shade]);
    }
    if(Math.abs(a[0])<bounds[0]&&Math.abs(a[1])<bounds[1]&&edges.length<360000)
     edges.push(a[0]*scale,bottom*scale,-a[1]*scale,a[0]*scale,h*scale,-a[1]*scale);
   }
   const xmin=Math.max(-bounds[0],item.xmin),xmax=Math.min(bounds[0],item.xmax);
   const zmin=Math.max(-bounds[1],item.zmin),zmax=Math.min(bounds[1],item.zmax);
   const step=Math.max(5,Math.sqrt(Math.max(1,(xmax-xmin)*(zmax-zmin))/20));
   for(let x=xmin;x<xmax&&used<quota;x+=step)for(let z=zmin;z<zmax&&used<quota;z+=step)
    if(inside([x,z],ring)&&!holes.some(hole=>inside([x,z],hole)))put(x,h,z,[.30,.47,.57]);
  }
 }
 {
  for(const road of data.roads||[]){
   if(["ferry","aerialway"].includes(road.kind))continue;
   const path=road.path.map(meters),major=/^(motorway|trunk|primary|secondary|tertiary)$/.test(road.kind);
   const pedestrian=/path|footway|pedestrian|cycleway|steps|track/.test(road.kind+" "+(road.subclass||""));
   const target=major?arterials:pedestrian?paths:streets;
   for(let i=1;i<path.length;i++){
    const clipped=clipSegment(path[i-1],path[i],bounds);if(!clipped)continue;
    for(const p of clipped)target.push(p[0]*scale,.002,-p[1]*scale);
   }
  }
  for(const label of data.labels||[]){
   const [x,z]=meters(label.location);
   if(Math.abs(x*scale)>2.15||Math.abs(z*scale)>1.3||labels.some(p=>p.name===label.name||Math.hypot(p.position[0]-x*scale,p.position[2]+z*scale)<.42))continue;
   labels.push({name:label.name,position:[x*scale,.035,-z*scale]});if(labels.length>=8)break;
  }
 }
 // Keep the entire provider route in the scene. The camera clips visibility, never the data.
 const totalLength=routeM.slice(1).reduce((sum,p,i)=>sum+Math.hypot(p[0]-routeM[i][0],p[1]-routeM[i][1]),0);
 const spacing=Math.max(2,totalLength/7500);
 const fullLine=[];
 for(let i=1;i<routeM.length;i++){
  const a=routeM[i-1],b=routeM[i],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
  fullLine.push(a[0]*scale,3*scale,-a[1]*scale,b[0]*scale,3*scale,-b[1]*scale);
  const count=Math.max(1,Math.ceil(length/spacing)),part=[];
  for(let j=0;j<=count;j++){
   const t=j/count,p=[(a[0]+(b[0]-a[0])*t)*scale,3*scale,-(a[1]+(b[1]-a[1])*t)*scale];
   const last=route.at(-1);if(!last||Math.hypot(...p.map((v,k)=>v-last[k]))>.001)route.push(p);
   part.push(p);
  }
  if(part.length>1)routeParts.push(part);
 }
 return {points,colors,fades,edges,streets,arterials,paths,labels,route,routeParts,origin,scale,extent,bounds,
  renderedBuildings:overview?0:buildings.length,visualMaxHeight,heightScale,fullLine};
}
export function createParticleCity(THREE,scene,camera=null){
 const group=new THREE.Group();scene.add(group);group.visible=false;
 const viewport={value:new THREE.Vector4(0,0,1,1)};
 function clipToCity(material){
  material.onBeforeCompile=shader=>{
   shader.uniforms.uCityViewport=viewport;
   shader.fragmentShader="uniform vec4 uCityViewport;"+String.fromCharCode(10)+shader.fragmentShader.replace(/void\s+main\(\s*\)\s*\{/,match=>match+" if(gl_FragCoord.x<uCityViewport.x||gl_FragCoord.y<uCityViewport.y||gl_FragCoord.x>uCityViewport.z||gl_FragCoord.y>uCityViewport.w)discard;");
  };
  material.customProgramCacheKey=()=>"jarvis-central-map-viewport-v1";
  return material;
 }
 const vertex=`
 attribute float aFade;varying vec3 vColor;varying float vFade;
 uniform float uSize;uniform float uMorph;uniform float uTime;
 float hash(float n){return fract(sin(n)*43758.5453);}
 vec3 energy(float seed){
  float a=hash(seed+1.)*6.2831853+uTime*.048;
  float lane=(hash(seed+2.)-.5)*.23;
  float radius=1.16+.19*sin(a*3.+seed*.013+uTime*.17)+lane;
  vec3 p=vec3(radius*cos(a),radius*sin(a)*.79,.38*sin(a*2.+seed*.013+uTime*.20));
  float t=floor(hash(seed+3.)*6.)*1.09+uTime*.034,c=cos(t),s=sin(t);
  p.xy=mat2(c,s,-s,c)*p.xy;
  t=.48+floor(hash(seed+3.)*6.)*.48;c=cos(t);s=sin(t);p.yz=mat2(c,s,-s,c)*p.yz;
  return p;
 }
 void main(){
  float seed=dot(position,vec3(123.4,711.7,341.2));
  float delay=hash(seed+4.)*.16;
  float t=smoothstep(delay,.92+delay*.5,uMorph);
  vec3 target=(modelMatrix*vec4(position,1.)).xyz;
  vec3 source=energy(seed);
  vec3 p=mix(source,target,t);
  float swirl=sin(t*3.14159265);
  p+=vec3(sin(seed+uTime*.7),cos(seed*.7+uTime*.5),sin(seed*.3))*swirl*.32;
  vColor=mix(vec3(.61,.80,.91),color,t);vFade=mix(.75,aFade,t);
  gl_Position=projectionMatrix*viewMatrix*vec4(p,1.);gl_PointSize=uSize;
 }`;
 const fragment=`varying vec3 vColor;varying float vFade;uniform float uOpacity;
 void main(){float r=length(gl_PointCoord-.5)*2.;if(r>1.)discard;
 float alpha=(1.-smoothstep(.45,1.,r))*uOpacity*vFade;gl_FragColor=vec4(vColor,alpha);}`;
 function pointsMaterial(size){
  return clipToCity(new THREE.ShaderMaterial({uniforms:{uSize:{value:size},uOpacity:{value:0},uMorph:{value:0},uTime:{value:0}},
   vertexShader:vertex,fragmentShader:fragment,vertexColors:true,transparent:true,depthWrite:false,
   blending:THREE.NormalBlending,toneMapped:false}));
 }
 const geometry=new THREE.BufferGeometry(),material=pointsMaterial(1.15),city=new THREE.Points(geometry,material);group.add(city);
 const lineMaterial=(color)=>clipToCity(new THREE.LineBasicMaterial({color,transparent:true,opacity:0,depthWrite:false,blending:THREE.NormalBlending,toneMapped:false}));
 const edgeG=new THREE.BufferGeometry(),edgeM=lineMaterial(0x88b1ba);
 const wire=new THREE.LineSegments(edgeG,edgeM);wire.renderOrder=1;group.add(wire);city.renderOrder=2;
 const streetsG=new THREE.BufferGeometry(),streetsM=lineMaterial(0x7599b0),streets=new THREE.LineSegments(streetsG,streetsM);group.add(streets);
 const routeG=new THREE.BufferGeometry(),routeM=pointsMaterial(1.8),routePoints=new THREE.Points(routeG,routeM);
 routePoints.renderOrder=6;routeM.depthTest=false;group.add(routePoints);
 const routeLineG=new THREE.BufferGeometry(),routeLineM=lineMaterial(0x16fa7a),routeLine=new THREE.LineSegments(routeLineG,routeLineM);routeLine.renderOrder=6;routeLineM.depthTest=false;group.add(routeLine);
 const sparksG=new THREE.BufferGeometry(),sparkPositions=new Float32Array(36*3),sparkColors=new Float32Array(36*3).fill(.9),sparkFades=new Float32Array(36).fill(1);
 sparksG.setAttribute("position",new THREE.BufferAttribute(sparkPositions,3));
 sparksG.setAttribute("color",new THREE.BufferAttribute(sparkColors,3));
 sparksG.setAttribute("aFade",new THREE.BufferAttribute(sparkFades,1));
 const sparksM=pointsMaterial(2.6),sparks=new THREE.Points(sparksG,sparksM);sparks.renderOrder=7;sparksM.depthTest=false;group.add(sparks);
 const pinsG=new THREE.BufferGeometry(),pinsM=lineMaterial(0x66f5bb),pins=new THREE.LineSegments(pinsG,pinsM);pins.renderOrder=8;pinsM.depthTest=false;group.add(pins);
 const architecture=new THREE.Group();group.add(architecture);architecture.add(city,wire);
 const arterialG=new THREE.BufferGeometry(),arterialM=lineMaterial(0xa1d4df),arterial=new THREE.LineSegments(arterialG,arterialM);group.add(arterial);
 const pathG=new THREE.BufferGeometry(),pathM=new THREE.LineDashedMaterial({color:0x5b8795,dashSize:.012,gapSize:.012,transparent:true,opacity:0,depthWrite:false,toneMapped:false});
 clipToCity(pathM);
 const footpaths=new THREE.LineSegments(pathG,pathM);group.add(footpaths);
 const labelGroup=new THREE.Group();group.add(labelGroup);
 let revision=-1,built=null,lastBudget=0;
 function attributes(g,positions,colors,fades){
  const count=positions.length/3;
  if(!g.getAttribute("position")||g.getAttribute("position").count<count){
   g.dispose();for(const name of Object.keys(g.attributes))g.deleteAttribute(name);
   const capacity=2**Math.ceil(Math.log2(Math.max(1,count)));
   g.setAttribute("position",new THREE.BufferAttribute(new Float32Array(capacity*3),3).setUsage(THREE.DynamicDrawUsage));
   g.setAttribute("color",new THREE.BufferAttribute(new Float32Array(capacity*3),3).setUsage(THREE.DynamicDrawUsage));
   g.setAttribute("aFade",new THREE.BufferAttribute(new Float32Array(capacity),1).setUsage(THREE.DynamicDrawUsage));
  }
  for(const [name,data] of [["position",positions],["color",colors],["aFade",fades]]){
   const attr=g.getAttribute(name);attr.array.fill(0);attr.array.set(data);attr.needsUpdate=true;
  }
  g.setDrawRange(0,count);g.computeBoundingSphere();
 }
 function lines(g,array){
  const count=array.length/3;
  if(!g.getAttribute("position")||g.getAttribute("position").count<count){
   g.dispose();for(const name of Object.keys(g.attributes))g.deleteAttribute(name);
   const capacity=2**Math.ceil(Math.log2(Math.max(1,count)));
   g.setAttribute("position",new THREE.BufferAttribute(new Float32Array(capacity*3),3).setUsage(THREE.DynamicDrawUsage));
  }
  const attr=g.getAttribute("position");attr.array.fill(0);attr.array.set(array);attr.needsUpdate=true;
  g.setDrawRange(0,count);g.computeBoundingSphere();
 }
 function dashedDistances(g){
  const position=g.getAttribute("position");
  let attr=g.getAttribute("lineDistance");
  if(!attr||attr.count!==position.count){
   attr=new THREE.BufferAttribute(new Float32Array(position.count),1).setUsage(THREE.DynamicDrawUsage);
   g.setAttribute("lineDistance",attr);
  }
  let total=0;attr.array.fill(0);
  for(let i=0;i<g.drawRange.count;i+=2){
   attr.array[i]=total;
   total+=Math.hypot(position.getX(i+1)-position.getX(i),position.getY(i+1)-position.getY(i),position.getZ(i+1)-position.getZ(i));
   attr.array[i+1]=total;
  }
  attr.needsUpdate=true;
 }
 return {update(state,mix,time,metrics){
  const data=state.cityScene;
  const budget=state.cityParticleBudget||36000;
  if(data&&(state.cityRevision!==revision||budget!==lastBudget)){
   lastBudget=budget;
   revision=state.cityRevision;built=buildCityPositions(data.context||{},data.path||[],data.view||"start",data.focus||null,{extent:data.extent,heightScale:DEFAULT_HEIGHT_SCALE,particleBudget:budget});
   attributes(geometry,built.points,built.colors,built.fades);
   lines(edgeG,built.edges);lines(streetsG,built.streets||[]);lines(arterialG,built.arterials||[]);
   lines(pathG,built.paths||[]);dashedDistances(pathG);
   for(const label of [...labelGroup.children]){
    label.material.map?.dispose();label.material.dispose();labelGroup.remove(label);
   }
   const endpointLabels=(data.path?.length?[{name:"起点 · "+(data.originName||"出发地"),point:data.path[0]},
    {name:"终点 · "+(data.destinationName||"目的地"),point:data.path.at(-1)}]:[]).map(item=>{
    const point=item.point;
    return {name:item.name,endpoint:true,position:[(point[0]-built.origin[0])*111320*Math.cos(built.origin[1]*Math.PI/180)*built.scale,.22,-(point[1]-built.origin[1])*111320*built.scale]};
   });
   for(const item of [...built.labels,...endpointLabels]){
    const canvas=document.createElement("canvas");canvas.width=256;canvas.height=48;
    const ctx=canvas.getContext("2d");ctx.font="24px Microsoft YaHei, sans-serif";ctx.textAlign="center";
    ctx.strokeStyle="#02090e";ctx.lineWidth=5;ctx.strokeText(item.name,128,31);
    ctx.fillStyle="#a9cad5";ctx.fillText(item.name,128,31);
    const texture=new THREE.CanvasTexture(canvas);
    const m=new THREE.SpriteMaterial({map:texture,transparent:true,depthTest:false,depthWrite:false,toneMapped:false,opacity:0});
    clipToCity(m);
    const sprite=new THREE.Sprite(m);sprite.position.fromArray(item.position);sprite.scale.set(item.endpoint?1.25:.90,item.endpoint ? .22 : .17,1);sprite.userData.endpoint=!!item.endpoint;sprite.renderOrder=9;labelGroup.add(sprite);
   }
   lines(routeLineG,built.fullLine||[]);
   const markers=[];
   for(const p of [data.path?.[0],data.path?.at(-1)]){
    if(!p)continue;
    const x=(p[0]-built.origin[0])*111320*Math.cos(built.origin[1]*Math.PI/180)*built.scale;
    const z=-(p[1]-built.origin[1])*111320*built.scale;

    for(let j=0;j<40;j++){
     const a=j/40*Math.PI*2,b=(j+1)/40*Math.PI*2;
     markers.push(x+Math.cos(a)*.035,.008,z+Math.sin(a)*.035,x+Math.cos(b)*.035,.008,z+Math.sin(b)*.035);
    }
    markers.push(x,0,z,x,.18,z);
   }
   lines(pinsG,markers);
   attributes(routeG,built.route.flat(),built.route.flatMap(()=>[.06,.95,.30]),built.route.map(()=>1));
   metrics.cityBuildings=built.renderedBuildings;
   metrics.cityRoads=data.context?.roads?.length||0;metrics.citySource=data.context?.status||"loading";
   metrics.cityRoutePoints=built.route.length;metrics.cityExtentMeters=built.extent;metrics.cityView=data.view||"start";
   metrics.cityParticles=built.points.length/3+built.route.length+36;
   metrics.cityRoadSegments=((built.streets||[]).length+(built.arterials||[]).length+(built.paths||[]).length)/6;
   metrics.cityCourtyards=(data.context?.buildings||[]).reduce((s,b)=>s+(b.holes?.length||0),0);
   metrics.cityTileZoom=data.context?.tile_zoom||null;metrics.cityLabels=built.labels.length;
   metrics.cityEndpointCount=endpointLabels.length;metrics.cityFullRouteSegments=(built.fullLine||[]).length/6;
  }
  group.visible=!!built&&mix>.001;if(!group.visible)return;
  const dprNow=metrics.pixelRatio||1,w=metrics.resolution[0]/dprNow,h=metrics.resolution[1]/dprNow;
  const left=document.querySelector(".left-rail")?.getBoundingClientRect().right||w*.20;
  const right=document.querySelector(".right-rail")?.getBoundingClientRect().left||w*.80;
  viewport.value.set((left+18)*dprNow,h*.28*dprNow,(right-18)*dprNow,h*.76*dprNow);
  metrics.cityViewport={left:left+18,right:right-18,top:h*.24,bottom:h*.72};
  state.cityFrame={origin:built.origin,extent:built.extent};
  metrics.cityFocus=built.origin;
  group.rotation.set(state.cityPitch||.62,-.25+(state.cityYaw||0),0);
  const heightScale=Math.max(1,Math.min(32,Number(state.cityHeightScale)||DEFAULT_HEIGHT_SCALE));
  architecture.scale.y=heightScale/DEFAULT_HEIGHT_SCALE;
  metrics.cityHeightScale=heightScale;metrics.cityVisualMaxHeight=built.visualMaxHeight*architecture.scale.y;
  metrics.cityYawTurns=(state.cityYaw||0)/(Math.PI*2);metrics.cityPitch=state.cityPitch||.62;
  metrics.cityZoom=state.cityZoom||1;metrics.cityPan=[state.cityPanX||0,state.cityPanY||0];
  group.scale.setScalar(.88*(state.cityZoom||1));group.position.set(state.cityPanX||0,-.24+(state.cityPanY||0),0);
  const arrival=THREE.MathUtils.smoothstep(mix,.63,1);
  const enter=THREE.MathUtils.smoothstep(mix,0,.18);
  material.uniforms.uOpacity.value=enter*.72;routeM.uniforms.uOpacity.value=enter*.95;
  edgeM.opacity=arrival*.58;streetsM.opacity=arrival*.46;arterialM.opacity=arrival*.72;pathM.opacity=arrival*.32;
  for(const label of labelGroup.children)label.material.opacity=arrival*.70;routeLineM.opacity=arrival*.90;pinsM.opacity=arrival*.95;
  sparksM.uniforms.uOpacity.value=arrival*.86;
  const dpr=metrics.pixelRatio||1;
  for(const m of [material,routeM,sparksM]){m.uniforms.uMorph.value=mix;m.uniforms.uTime.value=time;}
  material.uniforms.uSize.value=1.15*dpr;routeM.uniforms.uSize.value=1.8*dpr;sparksM.uniforms.uSize.value=2.6*dpr;
  const count=Math.min(36,Math.max(0,Math.floor(built.route.length/12)));
  sparksG.setDrawRange(0,count);
  for(let i=0;i<count;i++){
   const t=((i/count+time*.045)%1)*(built.route.length-1),a=Math.floor(t),b=Math.min(built.route.length-1,a+1),f=t-a;
   for(let k=0;k<3;k++)sparkPositions[i*3+k]=built.route[a][k]*(1-f)+built.route[b][k]*f;
  }
  sparksG.attributes.position.needsUpdate=true;
  if(camera&&data.path?.length){
   group.updateMatrixWorld(true);camera.updateMatrixWorld();
   metrics.cityEndpointProjection=[data.path[0],data.path.at(-1)].map(p=>{
    const v=new THREE.Vector3((p[0]-built.origin[0])*111320*Math.cos(built.origin[1]*Math.PI/180)*built.scale,.01,-(p[1]-built.origin[1])*111320*built.scale);
    v.applyMatrix4(group.matrixWorld).project(camera);
    return {x:v.x,y:v.y,visible:Math.abs(v.x)<1&&Math.abs(v.y)<1&&v.z>=-1&&v.z<=1};
   });
  }
 }};
}
