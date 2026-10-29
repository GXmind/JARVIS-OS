/* Explicit visual states, independent of audio devices and application transport. */
export const ACTIVITY_CODES={idle:0,listening:1,transcribing:2,thinking:3,speaking:4,modeling:5};
export function visualActivity(state){
 if(state.mapOnly||state.mapReady||state.mapTransfer&&!state.mapTransfer.finished||state.center?.active)return {name:"dedicated",code:0};
 const name=state.capturing?"listening":state.error?"error":state.activity||"idle";
 return {name,code:name==="error"?6:ACTIVITY_CODES[name]??0};
}
