import {buildCityPositions} from "./city_geometry.js";
self.onmessage=event=>{
 const {id,data,path,view,focus,options}=event.data,start=performance.now();
 try{
  const built=buildCityPositions(data,path,view,focus,options),buffers=[];
  for(const key of ["points","colors","fades","edges","streets","arterials","paths","fullLine"]){built[key]=new Float32Array(built[key]||[]);buffers.push(built[key].buffer);}
  built.routePositions=new Float32Array(built.route.flat());built.routeColors=new Float32Array(built.route.length*3);built.routeFades=new Float32Array(built.route.length).fill(1);
  for(let i=0;i<built.route.length;i++)built.routeColors.set([.06,.95,.30],i*3);
  const dust=[];
  for(const array of [built.streets,built.arterials,built.paths,built.edges,built.fullLine])for(let i=0;i+5<array.length&&dust.length<36000;i+=6){
   const length=Math.hypot(array[i+3]-array[i],array[i+4]-array[i+1],array[i+5]-array[i+2]),count=Math.min(8,Math.max(1,Math.ceil(length/.025)));
   for(let j=0;j<count&&dust.length<36000;j++)for(let k=0;k<3;k++)dust.push(array[i+k]+(array[i+3+k]-array[i+k])*j/count);
  }
  built.dustPositions=new Float32Array(dust);built.dustColors=new Float32Array(dust.length);built.dustFades=new Float32Array(dust.length/3).fill(1);
  for(let i=0;i<dust.length;i+=3)built.dustColors.set([.55,.80,.95],i);
  for(const key of ["routePositions","routeColors","routeFades","dustPositions","dustColors","dustFades"])buffers.push(built[key].buffer);
  self.postMessage({id,built,milliseconds:performance.now()-start},buffers);
 }catch(error){self.postMessage({id,error:String(error.message||error)});}
};
