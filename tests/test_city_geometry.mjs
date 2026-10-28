import assert from "node:assert/strict";
import {inside,buildCityPositions} from "../src/jarvis/presentation/web/assets/rendering/city_geometry.js";
import {extractTransit,resolveRouteCommand} from "../src/jarvis/presentation/web/assets/features/navigation/controller.js";
assert.equal(inside([1,1],[[0,0],[2,0],[2,2],[0,2]]),true);
assert.equal(inside([4,1],[[0,0],[2,0],[2,2],[0,2]]),false);
const path=[[120.60,31.31],[120.61,31.32]];
const result=buildCityPositions({buildings:[{footprint:[[120.601,31.311],[120.602,31.311],[120.602,31.312],[120.601,31.311]],height:45}],roads:[{path}]},path);
assert.ok(result.points.length>30);
assert.ok(result.points.filter((_,i)=>i%3===1).some(y=>y>0),"Buildings must have true height");
assert.ok(result.route.length>10);
const transit=extractTransit({distance:2100,time:900,path,segments:[{instruction:"地铁换乘"}]});
assert.equal(transit.seconds,900);
assert.equal(transit.steps[0].instruction,"地铁换乘");
console.log("3D footprint height, city particles and transit path checks passed.");
const defaults={default_origin:"F2 保存的地址"};
assert.equal(resolveRouteCommand({action:"route",destination:"虎丘景区"},defaults).origin,"F2 保存的地址");
assert.equal(resolveRouteCommand({action:"route",origin:"本次指定起点",destination:"虎丘景区"},defaults).origin,"本次指定起点");
assert.equal(resolveRouteCommand({action:"route",origin:"旧的默认地址",origin_source:"saved",destination:"虎丘景区"},defaults).origin,"F2 保存的地址");
console.log("Saved-origin fallback, latest saved address and explicit-origin precedence passed.");

const longRoute=[[120.60,31.31],[121.50,31.22]];
const localLong=buildCityPositions({buildings:[{footprint:[[120.601,31.311],[120.602,31.311],[120.602,31.312],[120.601,31.311]],height:45}],roads:[]},longRoute,"start");
assert.equal(localLong.extent,1600,"A long route must not shrink the default city");
assert.equal(result.scale,localLong.scale);
assert.ok(localLong.route.length<9000,"Whole-route grains must stay bounded without discarding the route");
assert.ok(localLong.route.some(p=>Math.abs(p[0])>2.4),"Offscreen route must remain available to pan into view");
assert.equal(localLong.fullLine.length,6);
assert.ok(Math.abs(localLong.route.at(-1)[0])>10,"The actual destination must not be clipped at the local street boundary");
const overview=buildCityPositions({},longRoute,"overview");
assert.ok(overview.extent>50000);
console.log("Street-scale city stays large for long routes; clipped point budget and overview are valid.");

assert.ok(result.streets.length>=6,"Road line geometry is independent from the building particle budget");
assert.ok(result.streets.every(Number.isFinite));
assert.equal(result.streets.length%6,0);
assert.ok(localLong.edges.length>0,"Architecture must retain visible roof and vertical edges");
console.log("Independent street network and architectural wire geometry passed.");

const outer=[[120.599,31.309],[120.601,31.309],[120.601,31.311],[120.599,31.311],[120.599,31.309]];
const hole=[[120.5996,31.3096],[120.5996,31.3104],[120.6004,31.3104],[120.6004,31.3096],[120.5996,31.3096]];
const shell={footprint:outer,holes:[hole],height:24,min_height:6};
const precise=buildCityPositions({buildings:[shell],roads:[]},[[120.6,31.31]],"start",null,{extent:1600,heightScale:16});
const physical=buildCityPositions({buildings:[shell],roads:[]},[[120.6,31.31]],"start",null,{extent:1600,heightScale:1});
assert.ok(precise.visualMaxHeight>physical.visualMaxHeight*10,"Default vertical emphasis must visibly raise architecture");
assert.equal(precise.renderedBuildings,1);
assert.ok(precise.points.filter((_,i)=>i%3===1).every(y=>y>=6*16*precise.scale-1e-9),"Elevated building parts may not grow to ground level");
const area=(1600/3.9),cos=Math.cos(31.31*Math.PI/180);
for(let i=0;i<precise.points.length;i+=3){
 const x=precise.points[i]*area,z=-precise.points[i+2]*area;
 if(Math.abs(x)<20&&Math.abs(z)<20)assert.fail("The open courtyard must not contain roof/facade particles");
}
const hierarchy=buildCityPositions({buildings:[],roads:[
 {kind:"primary",path:[[120.599,31.31],[120.601,31.31]]},
 {kind:"path",path:[[120.6,31.309],[120.6,31.311]]}
]},[[120.6,31.31]]);
assert.ok(hierarchy.arterials.length>0&&hierarchy.paths.length>0,"Road hierarchy must remain separate");
assert.equal(shell.height,24,"Visual height must never rewrite geographic source heights");
console.log("Courtyard holes, elevated bases, stronger visual height and road hierarchy passed.");

assert.ok(overview.route.every(p=>Math.abs(p[0])<1.65&&Math.abs(p[2])<1.1),"Full route must fit both endpoints with margin");
console.log("Full route retains offscreen segments and fits both endpoints in overview.");
