/* Street-scale 3D particle architecture; routes use screen-sized grains, never additive glow bands. */
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
  const r=q[i]/p[i];
  if(p[i]<0)low=Math.max(low,r);else high=Math.min(high,r);
  if(low>high)return null;
 }
 return [[a[0]+low*dx,a[1]+low*dy],[a[0]+high*dx,a[1]+high*dy]];
}
export function buildCityPositions(data,path,view="start",focus=null){
 const basis=path.length?path:(data.roads?.[0]?.path||data.buildings?.[0]?.footprint||[]);
 if(!basis.length)return {points:[],colors:[],fades:[],edges:[],route:[],routeParts:[],origin:[0,0],scale:1};
 const overview=view==="overview";
 const origin=overview?[(Math.min(...basis.map(p=>p[0]))+Math.max(...basis.map(p=>p[0])))/2,
  (Math.min(...basis.map(p=>p[1]))+Math.max(...basis.map(p=>p[1])))/2]:(focus||(view==="end"?basis.at(-1):basis[0]));
 const cos=Math.cos(origin[1]*Math.PI/180),meters=p=>[(p[0]-origin[0])*111320*cos,(p[1]-origin[1])*111320];
 const routeM=basis.map(meters);
 const extent=overview?Math.max(2600,...routeM.map(p=>Math.abs(p[0])*2),...routeM.map(p=>Math.abs(p[1])*2)):2600;
 const scale=3.9/extent,bounds=[2.4/scale,1.6/scale];
 const points=[],colors=[],fades=[],edges=[],streets=[],route=[],routeParts=[];
 function put(x,y,z,color){
  if(points.length>=135000||Math.abs(x)>bounds[0]||Math.abs(z)>bounds[1])return;
  const fade=Math.max(.05,1-Math.max(Math.abs(x)/bounds[0],Math.abs(z)/bounds[1])**6);
  points.push(x*scale,y*scale,-z*scale);colors.push(...color);fades.push(fade);
 }
 function edge(a,b,height){
  const clipped=clipSegment(a,b,bounds);if(!clipped||edges.length>180000)return;
  for(const p of clipped)edges.push(p[0]*scale,height*scale,-p[1]*scale);
 }
 function grains(a,b,height,color,spacing=10){
  const clipped=clipSegment(a,b,bounds);if(!clipped)return;
  [a,b]=clipped;
  const length=Math.hypot(b[0]-a[0],b[1]-a[1]),count=Math.min(400,Math.max(1,Math.ceil(length/spacing)));
  for(let i=0;i<count;i++){const t=i/count;put(a[0]+(b[0]-a[0])*t,height,a[1]+(b[1]-a[1])*t,color);}
 }
 if(!overview){
  const buildings=[...(data.buildings||[])].sort((a,b)=>{
   const center=r=>{const ring=r.footprint;return ring.reduce((s,p)=>s+Math.hypot(...meters(p)),0)/ring.length;};
   return center(a)-center(b);
  });
  for(const building of buildings){
   const ring=building.footprint.map(meters),holes=(building.holes||[]).map(h=>h.map(meters));
   const h=Math.min(180,Math.max(6,building.height||12))*8;
   for(let i=1;i<ring.length;i++){
    const a=ring[i-1],b=ring[i];
    edge(a,b,h);grains(a,b,h,[.58,.71,.74],9);
    // Keep facades open: architectural corners/roofs remain readable at neighborhood scale.
    const clipped=clipSegment(a,b,bounds);if(!clipped)continue;
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]),count=Math.max(1,Math.min(32,Math.ceil(length/10)));
    const shade=.5+.35*Math.abs((b[0]-a[0])/(length||1));
    for(let j=0;j<=count;j++){
     const t=j/count,x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;
     for(let y=0;y<h;y+=18)put(x,y,z,[.22*shade,.38*shade,.43*shade]);
    }
    if(Math.abs(a[0])<bounds[0]&&Math.abs(a[1])<bounds[1]){
     edges.push(a[0]*scale,0,-a[1]*scale,a[0]*scale,h*scale,-a[1]*scale);
    }
   }
   const xmin=Math.max(-bounds[0],Math.min(...ring.map(p=>p[0]))),xmax=Math.min(bounds[0],Math.max(...ring.map(p=>p[0])));
   const zmin=Math.max(-bounds[1],Math.min(...ring.map(p=>p[1]))),zmax=Math.min(bounds[1],Math.max(...ring.map(p=>p[1])));
   const step=Math.max(9,Math.sqrt(Math.max(1,(xmax-xmin)*(zmax-zmin))/12));
   for(let x=xmin;x<xmax;x+=step)for(let z=zmin;z<zmax;z+=step){
    if(inside([x,z],ring)&&!holes.some(hole=>inside([x,z],hole)))put(x,h,z,[.32,.46,.50]);
   }
  }
  for(const road of data.roads||[]){
   const path=road.path.map(meters);
   for(let i=1;i<path.length;i++){
    const clipped=clipSegment(path[i-1],path[i],bounds);
    if(clipped)for(const p of clipped)streets.push(p[0]*scale,.001,-p[1]*scale);
   }
  }
 }
 // Uniform metric spacing and clipped segments prevent thousands of coincident luminous dots.
 const spacing=overview?Math.max(12,extent/650):6;
 for(let i=1;i<routeM.length;i++){
  const clipped=clipSegment(routeM[i-1],routeM[i],bounds);if(!clipped)continue;
  const [a,b]=clipped,length=Math.hypot(b[0]-a[0],b[1]-a[1]);
  const count=Math.min(800,Math.max(1,Math.ceil(length/spacing))),part=[];
  for(let j=0;j<=count;j++){
   const t=j/count,p=[(a[0]+(b[0]-a[0])*t)*scale,5*scale,-(a[1]+(b[1]-a[1])*t)*scale];
   const last=route.at(-1);if(!last||Math.hypot(...p.map((v,k)=>v-last[k]))>.002)route.push(p);
   part.push(p);
  }
  if(part.length>1)routeParts.push(part);
 }
 return {points,colors,fades,edges,streets,route,routeParts,origin,scale,extent,bounds};
}
export function createParticleCity(THREE,scene){
 const group=new THREE.Group();scene.add(group);group.visible=false;
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
  return new THREE.ShaderMaterial({uniforms:{uSize:{value:size},uOpacity:{value:0},uMorph:{value:0},uTime:{value:0}},
   vertexShader:vertex,fragmentShader:fragment,vertexColors:true,transparent:true,depthWrite:false,
   blending:THREE.NormalBlending,toneMapped:false});
 }
 const geometry=new THREE.BufferGeometry(),material=pointsMaterial(1.15),city=new THREE.Points(geometry,material);group.add(city);
 const lineMaterial=(color)=>new THREE.LineBasicMaterial({color,transparent:true,opacity:0,depthWrite:false,blending:THREE.NormalBlending,toneMapped:false});
 const edgeG=new THREE.BufferGeometry(),edgeM=lineMaterial(0x88b1ba);
 const wire=new THREE.LineSegments(edgeG,edgeM);wire.renderOrder=1;group.add(wire);city.renderOrder=2;
 const streetsG=new THREE.BufferGeometry(),streetsM=lineMaterial(0x9bc5c9),streets=new THREE.LineSegments(streetsG,streetsM);group.add(streets);
 const routeG=new THREE.BufferGeometry(),routeM=pointsMaterial(1.8),routePoints=new THREE.Points(routeG,routeM);
 routePoints.renderOrder=6;routeM.depthTest=false;group.add(routePoints);
 const routeLineG=new THREE.BufferGeometry(),routeLineM=lineMaterial(0x16fa7a),routeLine=new THREE.LineSegments(routeLineG,routeLineM);routeLine.renderOrder=6;routeLineM.depthTest=false;group.add(routeLine);
 const sparksG=new THREE.BufferGeometry(),sparkPositions=new Float32Array(36*3),sparkColors=new Float32Array(36*3).fill(.9),sparkFades=new Float32Array(36).fill(1);
 sparksG.setAttribute("position",new THREE.BufferAttribute(sparkPositions,3));
 sparksG.setAttribute("color",new THREE.BufferAttribute(sparkColors,3));
 sparksG.setAttribute("aFade",new THREE.BufferAttribute(sparkFades,1));
 const sparksM=pointsMaterial(2.6),sparks=new THREE.Points(sparksG,sparksM);sparks.renderOrder=7;sparksM.depthTest=false;group.add(sparks);
 const pinsG=new THREE.BufferGeometry(),pinsM=lineMaterial(0x66f5bb),pins=new THREE.LineSegments(pinsG,pinsM);pins.renderOrder=8;pinsM.depthTest=false;group.add(pins);
 let revision=-1,built=null;
 function attributes(g,positions,colors,fades){
  g.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));
  g.setAttribute("color",new THREE.Float32BufferAttribute(colors,3));
  g.setAttribute("aFade",new THREE.Float32BufferAttribute(fades,1));g.computeBoundingSphere();
 }
 function lines(g,array){g.setAttribute("position",new THREE.Float32BufferAttribute(array,3));g.computeBoundingSphere();}
 return {update(state,mix,time,metrics){
  const data=state.cityScene;
  if(data&&state.cityRevision!==revision){
   revision=state.cityRevision;built=buildCityPositions(data.context||{},data.path||[],data.view||"start",data.focus||null);
   attributes(geometry,built.points,built.colors,built.fades);
   lines(edgeG,built.edges);lines(streetsG,built.streets||[]);
   const routeSegments=[];
   for(const part of built.routeParts)for(let i=1;i<part.length;i++)routeSegments.push(...part[i-1],...part[i]);
   lines(routeLineG,routeSegments);
   const markers=[];
   for(const p of [data.path?.[0],data.path?.at(-1)]){
    if(!p)continue;
    const x=(p[0]-built.origin[0])*111320*Math.cos(built.origin[1]*Math.PI/180)*built.scale;
    const z=-(p[1]-built.origin[1])*111320*built.scale;
    if(Math.abs(x)>2.4||Math.abs(z)>1.6)continue;
    for(let j=0;j<40;j++){
     const a=j/40*Math.PI*2,b=(j+1)/40*Math.PI*2;
     markers.push(x+Math.cos(a)*.035,.008,z+Math.sin(a)*.035,x+Math.cos(b)*.035,.008,z+Math.sin(b)*.035);
    }
    markers.push(x,0,z,x,.18,z);
   }
   lines(pinsG,markers);
   attributes(routeG,built.route.flat(),built.route.flatMap(()=>[.06,.95,.30]),built.route.map(()=>1));
   metrics.cityBuildings=data.view==="overview"?0:data.context?.buildings?.length||0;
   metrics.cityRoads=data.context?.roads?.length||0;metrics.citySource=data.context?.status||"loading";
   metrics.cityRoutePoints=built.route.length;metrics.cityExtentMeters=built.extent;metrics.cityView=data.view||"start";
   metrics.cityParticles=built.points.length/3+built.route.length+36;
   metrics.cityRoadSegments=(built.streets||[]).length/6;
  }
  group.visible=!!built&&mix>.001;if(!group.visible)return;
  group.rotation.set(.50,-.25+(state.cityYaw||0),0);
  group.scale.setScalar(.88*(state.cityZoom||1));group.position.y=-.16;
  const arrival=THREE.MathUtils.smoothstep(mix,.63,1);
  const enter=THREE.MathUtils.smoothstep(mix,0,.18);
  material.uniforms.uOpacity.value=enter*.72;routeM.uniforms.uOpacity.value=enter*.95;
  edgeM.opacity=arrival*.64;streetsM.opacity=arrival*.63;routeLineM.opacity=arrival*.90;pinsM.opacity=arrival*.95;
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
 }};
}
