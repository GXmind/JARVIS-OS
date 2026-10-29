/* Shared timing contract for departure and destination assembly; no DOM/GPU. */
const clamp=x=>Math.max(0,Math.min(1,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
export function transferFrame(transfer,stamp){
 if(!transfer||transfer.finished)return {active:false,phase:"idle",progress:1,flight:0,energyMix:null,direction:{x:1,y:0}};
 const progress=clamp((stamp-transfer.started)/(transfer.duration||1900));
 const departing=transfer.phase==="depart";
 return {active:progress<1,phase:transfer.phase,progress,flight:departing?ease(progress):1-ease((progress-.22)/.78),
  energyMix:departing?1-ease((progress-.5)/.5):1,direction:transfer.direction||{x:1,y:0}};
}
