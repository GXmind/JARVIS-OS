/* Pure deterministic particle sampling; no DOM, network or GPU. */
export const PALETTES={galaxy:[.46,.42,1],violet:[.66,.34,1],rose:[1,.40,.72],gold:[1,.76,.44],ice:[.64,.73,1]};
const tau=Math.PI*2;
export function buildCenter(plan,budget=20000,glyphs={}){
 if(!plan||!Array.isArray(plan.nodes)||!plan.nodes.length||plan.nodes.length>32)throw Error("Invalid particle scene");
 const count=Math.max(1000,Math.min(24000,Math.floor(budget))),positions=new Float32Array(count*3),colors=new Float32Array(count*3),centers=new Float32Array(count*3),motion=new Float32Array(count*2),seeds=new Float32Array(count),nodes=new Float32Array(count);
 let rng=73913;const rand=()=>((rng=(Math.imul(rng,1664525)+1013904223)>>>0)/4294967296),bound=[Infinity,Infinity,Infinity,-Infinity,-Infinity,-Infinity];
 const resolvedColors=plan.nodes.map(node=>/^#[0-9a-f]{6}$/i.test(node.color||"")?[1,3,5].map(i=>parseInt(node.color.slice(i,i+2),16)/255):PALETTES[node.color]||PALETTES.galaxy);
 const pascal=Array.from({length:8},(_,n)=>Array.from({length:n+1},(_,k)=>{let value=1;for(let i=1;i<=k;i++)value=value*(n-i+1)/i;return value;}));
 function bezier(points,u,v,rows=4,cols=4){const basis=(t,n)=>pascal[n].map((c,i)=>c*Math.pow(t,i)*Math.pow(1-t,n-i)),x=basis(u,cols-1),y=basis(v,rows-1),out=[0,0,0];for(let j=0;j<rows;j++)for(let i=0;i<cols;i++)for(let k=0;k<3;k++)out[k]+=points[j*cols+i][k]*x[i]*y[j];return out;}
 function curve(points,u,closed){
  const n=points.length,t=u*(closed?n:n-1),i=closed?Math.floor(t)%n:Math.min(n-2,Math.floor(t)),f=t-Math.floor(t);
  const point=k=>points[closed?(k+n)%n:Math.max(0,Math.min(n-1,k))],p0=point(i-1),p1=point(i),p2=point(i+1),p3=point(i+2);
  return [0,1,2].map(k=>.5*((2*p1[k])+(-p0[k]+p2[k])*f+(2*p0[k]-5*p1[k]+4*p2[k]-p3[k])*f*f+(-p0[k]+3*p1[k]-3*p2[k]+p3[k])*f*f*f));
 }
 const weights=plan.nodes.map((n,i)=>{const scale=n.scale||[1,1,1];return Math.pow(glyphs._weights?.[i]||Math.max(.03,scale[0]*scale[1]+scale[0]*scale[2]+scale[1]*scale[2]),.65);});
 const totalWeight=weights.reduce((a,b)=>a+b,0),base=Math.min(240,Math.floor(count/plan.nodes.length*.3)),indices=new Uint8Array(count);let offset=0;
 for(let index=0;index<plan.nodes.length;index++){const n=index===plan.nodes.length-1?count-offset:base+Math.floor((count-base*plan.nodes.length)*weights[index]/totalWeight);indices.fill(index,offset,offset+n);offset+=n;}
 for(let i=0;i<count;i++){
  const nodeIndex=indices[i],node=plan.nodes[nodeIndex],u=rand(),v=rand(),w=rand(),angle=u*tau;let p,customColor=null;
  if(node.shape==="sphere"){const y=v*2-1,r=Math.sqrt(1-y*y);p=[Math.cos(angle)*r,y,Math.sin(angle)*r];}
  else if(node.shape==="box"){
   const face=Math.floor(u*6),k=Math.floor(face/2);p=[v*2-1,w*2-1,rand()*2-1];p[k]=face%2?1:-1;
   if(w<.22)p[(k+1)%3]=v>.5?1:-1;
  }else if(node.shape==="patch")p=bezier(node.control,u,v,node.rows||4,node.cols||4);
  else if(node.shape==="curve"){
   const start=curve(node.points,u,node.closed),next=curve(node.points,Math.min(.99999,u+.001),node.closed),d=next.map((x,k)=>x-start[k]),l=Math.hypot(...d)||1;
   const tangent=d.map(x=>x/l),ref=Math.abs(tangent[1])>.9?[1,0,0]:[0,1,0],cross=(x,y)=>[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]],normal=cross(tangent,ref),length=Math.hypot(...normal)||1,n=normal.map(x=>x/length),binormal=cross(tangent,n);
   p=start.map((x,k)=>x+(n[k]*Math.cos(v*tau)+binormal[k]*Math.sin(v*tau))*(node.radius||.025));
  }else if(node.shape==="lathe"){
   const t=v*(node.profile.length-1),i=Math.min(node.profile.length-2,Math.floor(t)),f=t-i,aa=node.profile[i],bb=node.profile[i+1],r=aa[0]*(1-f)+bb[0]*f;p=[r*Math.cos(angle),aa[1]*(1-f)+bb[1]*f,r*Math.sin(angle)];
  }else if(node.shape==="mesh"){
   const face=node.faces[Math.floor(u*node.faces.length)],aa=node.vertices[face[0]],bb=node.vertices[face[1]],cc=node.vertices[face[2]],s=Math.sqrt(v);p=[0,1,2].map(k=>(1-s)*aa[k]+s*(1-w)*bb[k]+s*w*cc[k]);
  }else if(node.shape==="drawing"){
   const mask=glyphs[nodeIndex]||[[0,0,.5,.5,1]],point=mask[Math.floor(u*mask.length)];p=[point[0],point[1],(w-.5)*.025];customColor=point.slice(2,5);
   for(let k=0;k<2;k++){bound[k]=Math.min(bound[k],-2);bound[k+3]=Math.max(bound[k+3],2);}
  }else if(node.shape==="torus"){const b=v*tau,r=1+.07*Math.cos(b);p=[r*Math.cos(angle),.07*Math.sin(b),r*Math.sin(angle)];}
  else if(node.shape==="cone"||node.shape==="cylinder"){
   const radius=node.shape==="cone"?1-v:1;p=[Math.cos(angle)*radius,v*2-1,Math.sin(angle)*radius];
   if(w<.12){const r=Math.sqrt(v);p=[Math.cos(angle)*r,-1,Math.sin(angle)*r];}
  }else if(node.shape==="helix"){
   const y=(v*2-1)*1.6,b=y*5,sign=u>.5?1:-1,r=w<.20?rand()*2-1:sign;p=[Math.cos(b)*.56*r,y,Math.sin(b)*.56*r];
  }else if(node.shape==="heart"){
   const t=angle,k=.75+v*.25;p=[Math.pow(Math.sin(t),3)*k,(13*Math.cos(t)-5*Math.cos(2*t)-2*Math.cos(3*t)-Math.cos(4*t))/16*k,(w-.5)*.35*Math.sin(t)];
  }else if(node.shape==="galaxy"){
   const radius=Math.pow(v,.58)*2,arm=Math.floor(u*5),b=radius*2.2+arm*tau/5+(w-.5)*.28;p=[Math.cos(b)*radius,(rand()-.5)*.12,Math.sin(b)*radius];
  }else if(node.shape==="wave"){const x=(u-.5)*3,z=(v-.5)*3;p=[x,Math.sin(x*3)*Math.cos(z*2)*.3,z];}
  else if(node.shape==="text"){
   const mask=glyphs[node.text]||[[0,0]],point=mask[Math.floor(u*mask.length)];p=[point[0],point[1],(w-.5)*.08];
  }else throw Error("Unsupported particle primitive");
  const scale=node.scale||[1,1,1],rot=node.rotation||[0,0,0],center=node.position||[0,0,0];p=p.map((x,k)=>x*scale[k]);
  for(let axis=0;axis<3;axis++){const b=(axis+1)%3,c=(axis+2)%3,s=Math.sin(rot[axis]),q=Math.cos(rot[axis]),x=p[b],y=p[c];p[b]=x*q-y*s;p[c]=x*s+y*q;}
  const color=customColor||resolvedColors[nodeIndex],white=Math.pow(rand(),3)*.6;
  for(let k=0;k<3;k++){const x=p[k]+center[k];if(!Number.isFinite(x))throw Error("Non-finite particle coordinate");positions[i*3+k]=x;centers[i*3+k]=(node.pivot||center)[k];colors[i*3+k]=color[k]*(1-white)+white;bound[k]=Math.min(bound[k],x);bound[k+3]=Math.max(bound[k+3],x);}
  nodes[i]=nodeIndex;motion[i*2]=Math.max(0,["none","spin","orbit","bob","flap","flow","pulse"].indexOf(node.motion));motion[i*2+1]=.7/Math.pow(Math.max(.5,Math.hypot(...center)),1.5);seeds[i]=rand();
 }
 const center=[0,1,2].map(k=>(bound[k]+bound[k+3])/2),radius=Math.max(.2,...[0,1,2].map(k=>(bound[k+3]-bound[k])/2)),fit=1.7/radius;
 for(let i=0;i<count;i++)for(let k=0;k<3;k++){positions[i*3+k]=(positions[i*3+k]-center[k])*fit;centers[i*3+k]=(centers[i*3+k]-center[k])*fit;}
 return {positions,colors,centers,motion,seeds,nodes,count,frame:{center,fit}};
}
