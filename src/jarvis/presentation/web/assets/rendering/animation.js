/* Arbitrary transform tracks are data; no generated JavaScript is executed. */
const defaults={move:[0,0,0],turn:[0,0,0],stretch:[1,1,1]};
export function sampleTrack(node,time){
 const frames=node.frames;if(!frames?.length)return defaults;
 const end=frames.at(-1).t,t=node.loop===false?Math.min(time,end):time%end;
 let right=frames.findIndex(f=>f.t>t);if(right<0)right=frames.length-1;
 const a=frames[Math.max(0,right-1)],b=frames[right],fraction=a===b?0:(t-a.t)/(b.t-a.t),f=Math.max(0,Math.min(1,fraction));
 return Object.fromEntries(Object.entries(defaults).map(([key,fallback])=>[key,fallback.map((_,i)=>(a[key]||fallback)[i]*(1-f)+(b[key]||fallback)[i]*f)]));
}
