/* Screen-space glyph particles assemble into the destination interface, after the map stream arrives. */
export function createAssembly(THREE){
 const scene=new THREE.Scene(),camera=new THREE.Camera(),geometry=new THREE.BufferGeometry();
 const material=new THREE.ShaderMaterial({uniforms:{uProgress:{value:0},uDirection:{value:new THREE.Vector2(-1,0)},uDpr:{value:1}},
  vertexShader:`attribute vec2 aTarget;attribute float aSeed;uniform float uProgress;uniform vec2 uDirection;uniform float uDpr;varying float vAlpha;
   void main(){float t=smoothstep(aSeed*.16,.92+aSeed*.07,uProgress);vec2 direction=normalize(uDirection+vec2(.00001));vec2 edge=direction/max(abs(direction.x),abs(direction.y))*1.12;
    vec2 p=mix(edge,aTarget,t);p+=vec2(-direction.y,direction.x)*sin(t*12.+aSeed*60.)*.065*sin(t*3.14159265);
    gl_Position=vec4(p,0.,1.);gl_PointSize=(1.1+sin(t*3.14159265)*.7)*uDpr;vAlpha=smoothstep(0.,.10,t)*(1.-smoothstep(.86,1.,t));}`,
  fragmentShader:`varying float vAlpha;void main(){float r=length(gl_PointCoord-.5)*2.;gl_FragColor=vec4(.58,.88,1.,(1.-smoothstep(.25,1.,r))*vAlpha);}`,
  transparent:true,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});
 const points=new THREE.Points(geometry,material);points.frustumCulled=false;scene.add(points);let key=null,count=0;
 function sample(width,height){
  const targets=[],seeds=[],canvas=document.createElement("canvas");
  for(const el of document.querySelectorAll(".brand strong,.brand small,#replicaStatus,#returnPrimary,.section-heading,.trip-location small,.trip-location span,.travel-choice strong,.travel-choice span,.travel-choice small,#cityViewLabel,.map-tools,.replica-caption")){
   if(targets.length>=4800)break;const rect=el.getBoundingClientRect();if(!rect.width||!rect.height)continue;
   canvas.width=Math.min(320,Math.ceil(rect.width));canvas.height=Math.min(26,Math.ceil(rect.height));
   const ctx=canvas.getContext("2d",{willReadFrequently:true}),style=getComputedStyle(el);ctx.font=style.font||"10px monospace";ctx.fillStyle="#fff";ctx.textBaseline="top";
   ctx.fillText(el.textContent.trim().slice(0,44),0,1);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
   for(let y=0;y<canvas.height;y+=2)for(let x=0;x<canvas.width&&targets.length<4800;x+=2)if(pixels[(y*canvas.width+x)*4+3]>60){targets.push((rect.left+x)/width*2-1,1-(rect.top+y)/height*2);seeds.push(((x*17+y*31+targets.length)%101)/101);}
  }
  count=seeds.length;geometry.dispose();for(const name of Object.keys(geometry.attributes))geometry.deleteAttribute(name);
  geometry.setAttribute("position",new THREE.BufferAttribute(new Float32Array(count*3),3));geometry.setAttribute("aTarget",new THREE.BufferAttribute(new Float32Array(targets),2));geometry.setAttribute("aSeed",new THREE.BufferAttribute(new Float32Array(seeds),1));
 }
 return {update(state,transfer,width,height,dpr,metrics){
  scene.visible=state.mapOnly&&transfer.active&&transfer.phase==="arrive";
  if(!scene.visible)return;
  if(key!==state.mapTransfer.started){key=state.mapTransfer.started;sample(width,height);}
  material.uniforms.uProgress.value=Math.max(0,Math.min(1,(transfer.progress-.12)/.88));material.uniforms.uDirection.value.set(transfer.direction.x,transfer.direction.y);material.uniforms.uDpr.value=dpr;metrics.assemblyParticles=count;
 },render(renderer){if(!scene.visible)return;const clear=renderer.autoClear;renderer.autoClear=false;renderer.render(scene,camera);renderer.autoClear=clear;},close(){geometry.dispose();material.dispose();}};
}
