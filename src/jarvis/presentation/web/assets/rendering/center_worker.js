import {buildCenter,PALETTES} from "./center_geometry.js";
self.onmessage=event=>{
 const {id,plan,budget}=event.data;
 try{
  const glyphs={_weights:{}},sampleBudget=Math.max(1800,Math.floor(60000/Math.max(1,plan.nodes.filter(n=>["drawing","text"].includes(n.shape)).length)));
  let seed=8191;const random=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
  function collect(mask,point,seen){if(mask.length<sampleBudget)mask.push(point);else {const i=Math.floor(random()*seen);if(i<sampleBudget)mask[i]=point;}}
  const css=color=>{const rgb=PALETTES[color];return rgb?"rgb("+rgb.map(v=>Math.round(v*255)).join(",")+")":color||"#a29bff";};
  for(const [index,node] of plan.nodes.entries()){
   if(node.shape==="drawing"){
    const size=768,canvas=new OffscreenCanvas(size,size),ctx=canvas.getContext("2d",{willReadFrequently:true}),box=node.viewBox;
    ctx.scale(size/box[2],size/box[3]);ctx.translate(-box[0],-box[1]);ctx.lineJoin="round";ctx.lineCap="round";
    for(const item of node.paths){const path=new Path2D(item.d);ctx.fillStyle=ctx.strokeStyle=css(item.color);ctx.lineWidth=item.width;if(item.fill)ctx.fill(path);if(item.stroke)ctx.stroke(path);}
    const pixels=ctx.getImageData(0,0,size,size).data,mask=[];let seen=0;
    for(let y=0;y<size;y+=2)for(let x=0;x<size;x+=2){const i=(y*size+x)*4;if(pixels[i+3]>48)collect(mask,[(x/size-.5)*4,(.5-y/size)*4,pixels[i]/255,pixels[i+1]/255,pixels[i+2]/255],++seen);}
    if(!mask.length)throw Error("自由路径没有产生可见图形，请修改提示词重试。");glyphs[index]=mask;glyphs._weights[index]=seen;
   }
   if(node.shape!=="text")continue;
   const canvas=new OffscreenCanvas(768,128),ctx=canvas.getContext("2d",{willReadFrequently:true});ctx.font="bold 72px Microsoft YaHei, sans-serif";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillStyle="#fff";ctx.fillText(node.text||"JARVIS",384,64,730);
   const pixels=ctx.getImageData(0,0,768,128).data,mask=[];let seen=0;
   for(let y=0;y<128;y+=2)for(let x=0;x<768;x+=2)if(pixels[(y*768+x)*4+3]>80)collect(mask,[(x-384)/190,(64-y)/190],++seen);
   glyphs[node.text]=mask.length?mask:[[0,0]];glyphs._weights[index]=seen;
  }
  const data=buildCenter(plan,budget,glyphs);self.postMessage({id,data},Object.values(data).filter(v=>v instanceof Float32Array).map(v=>v.buffer));
 }catch(error){self.postMessage({id,error:String(error.message||error)});}
};
