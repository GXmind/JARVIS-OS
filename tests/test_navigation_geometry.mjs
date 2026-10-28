import assert from "node:assert/strict";
import {coordinates,extractRoute,screenPath,pointAt,routeParticles} from "../src/jarvis/presentation/web/assets/features/navigation/controller.js";
assert.deepEqual(coordinates({lng:120.5,lat:31.3}),[120.5,31.3]);
assert.deepEqual(coordinates({getLng:()=>120.6,getLat:()=>31.4}),[120.6,31.4]);
assert.equal(coordinates({lng:null,lat:null}),null);
assert.equal(coordinates([999,31]),null);
assert.equal(coordinates(","),null);
const route=extractRoute({distance:1000,time:180,steps:[
 {path:[[120.1,31.1],[120.2,31.2]],instruction:"向北行驶"},
 {path:[[120.2,31.2],[120.3,31.3]],instruction:"到达终点"}
]});
assert.equal(route.path.length,3);
assert.equal(route.distance,1000);
assert.equal(route.steps.length,2);
assert.throws(()=>extractRoute({steps:[]}));
const pixelPath=screenPath([[0,0],[0,0],[3,4]]);
assert.equal(pixelPath.length,5);
assert.deepEqual(pointAt(pixelPath,2.5),[1.5,2]);
assert.deepEqual(pointAt(pixelPath,100),[3,4]);
assert.equal(pointAt(screenPath([[1,1]]),0),null);
console.log("Navigation coordinate, real-path extraction and particle interpolation checks passed.");
const grains=routeParticles(screenPath([[0,0],[100,0],[100,100]]),2,80);
assert.equal(grains.length,80);
assert.equal(grains[0].x,0);
assert.equal(grains.at(-1).y,100);
assert.ok(grains.every(p=>p.x===100||p.y===0),"Particles must stay on the supplied route");
assert.deepEqual(routeParticles(screenPath([])),[]);
console.log("Fine route particles follow projected coordinates and obey the particle budget.");
