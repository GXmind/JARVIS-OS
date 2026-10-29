export const ribbonGLSL=`
uniform float uTime; uniform float uPhase; uniform float uLevel; uniform float uMapMix; uniform float uActivity; uniform float uCoreFade;
const float PI=3.14159265359;
mat3 rotX(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
mat3 rotY(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
mat3 rotZ(float a){float c=cos(a),s=sin(a);return mat3(c,s,0.,-s,c,0.,0.,0.,1.);}
vec3 ribbon(float t,float lane,float seed){
 float speed=uTime*.075,s=seed*1.618;
 float width=.17+.055*sin(t*2.+s+uTime*.31)+uPhase*.048;
 float radius=1.16+.20*sin(t*3.+s+uTime*.17)+lane*width;
 radius+=uPhase*.075*sin(t*5.-uTime*.35+s)+uLevel*.075*sin(t*4.+s);
 float a=t+.19*sin(t*2.+s+uTime*.08);
 vec3 p=vec3(radius*cos(a),radius*sin(a)*(.79+.05*sin(s)),.38*sin(t*2.+s+uTime*.20)+lane*.065*cos(t*3.+s));
 p=rotX(.48+seed*.48+uPhase*.18*sin(s))*rotZ(seed*1.09+speed*.26)*p;
 p=rotY(speed*.42+sin(uTime*.09)*.2)*p;
 p.y+=.04*sin(uTime*.6+s);
 float listen=max(0.,1.-abs(uActivity-1.)),transcribe=max(0.,1.-abs(uActivity-2.)),think=max(0.,1.-abs(uActivity-3.)),speak=max(0.,1.-abs(uActivity-4.)),model=max(0.,1.-abs(uActivity-5.));
 vec3 listening=rotX(.50)*vec3(cos(t)*(1.35+uLevel*.23),sin(t)*(1.35+uLevel*.23),sin(t*4.+uTime*1.8+s)*(.08+uLevel*.18)+lane*.10);
 vec3 thinking=rotY(uTime*.45+seed*.3)*rotX(seed*.72)*vec3(cos(t)*(.78+lane*.10),sin(t)*(.78+lane*.10),sin(t*3.-uTime*1.8+s)*.28);
 vec3 voice=p*(1.+.12*sin(t*3.-uTime*2.)+.18*uLevel);voice.y+=sin(t*5.-uTime*2.+s)*(.06+uLevel*.25);
 p=mix(p,listening,listen*.90);p=mix(p,rotZ(uTime*.34)*p*vec3(.85,1.15,.85),transcribe*.8);
 p=mix(p,thinking,think*.94);p=mix(p,voice,speak*.95);p=mix(p,rotY(uTime*.7)*vec3(cos(t)*.8,sin(t*2.+s)*1.3,sin(t)*.8),model*.9);
 // Unfurl the curved energy ribbons into a thin, wide plane before dissolving.
 vec3 plane=vec3((t/PI-1.)*2.25,lane*.40+sin(t*2.+s)*.38,0.);
 return mix(p,plane,smoothstep(0.,1.,uMapMix));

}
`;
export const meshVertex=ribbonGLSL+`
uniform float uSeed; varying vec2 vUv; varying vec3 vWorld;
void main(){vUv=uv;vec3 p=ribbon(uv.x*PI*2.,(uv.y-.5)*2.,uSeed);
 vec4 world=modelMatrix*vec4(p,1.);vWorld=world.xyz;gl_Position=projectionMatrix*viewMatrix*world;}
`;
export const meshFragment=`
uniform float uTime;uniform float uSeed;uniform float uPhase;uniform float uMapMix;uniform float uCoreFade;
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
 vec3 ice=vec3(.25,.25,1.),pearl=vec3(.91,.82,1.),warm=vec3(.98,.31,.66);
 float tint=.5+.5*sin(uSeed*2.1+vUv.x*4.);
 vec3 color=mix(ice,pearl,.34+.35*tint);
 if(uSeed>3.4)color=mix(color,warm,.40+.25*sin(vUv.x*6.+uSeed));
 color=mix(color,vec3(.65,.68,1.),uPhase*.12);
 float intensity=.65+fibers*1.1+fine*.02+fresnel*.45+grain*.06;
 float alpha=edge*(.065+fibers*.10+fresnel*.070)*flow;
 gl_FragColor=vec4(color*intensity*1.5,alpha*(1.-uMapMix)*uCoreFade);
}
`;
export const pointsVertex=ribbonGLSL+`
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
 vColor=mix(vec3(.35,.29,1.),vec3(.94,.86,1.),aSeed.w);
 if(aSeed.z>.85 && uMode>1.5)vColor=mix(vColor,vec3(1.,.42,.68),.48);
 vAlpha=(.16+pow(aSeed.y,2.)*.65)*(.78+.22*sin(uTime*.6+aSeed.x*40.));
 if(uMode<.5)vAlpha*=.66;else if(uMode<2.5)vAlpha*=(1.-uMapMix)*uCoreFade;
}
`;
export const pointsFragment=`
varying vec3 vColor;varying float vAlpha;
void main(){
 float r=length(gl_PointCoord-.5)*2.;
 float soft=exp(-r*r*4.2)*(1.-smoothstep(.65,1.,r));
 float center=exp(-r*r*29.);
 gl_FragColor=vec4(vColor*(1.1+center*1.6),soft*vAlpha);
}
`;
export const screenVertex=`
varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}
`;
export const thresholdFragment=`
uniform sampler2D uSource;varying vec2 vUv;
void main(){
 vec3 color=texture2D(uSource,vUv).rgb;
 float bright=max(max(color.r,color.g),color.b);
 gl_FragColor=vec4(color*smoothstep(.48,1.12,bright),1.);
}
`;
export const blurFragment=`
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
export const combineFragment=`
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
