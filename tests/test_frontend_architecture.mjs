import assert from "node:assert/strict";
import {readFileSync,readdirSync,statSync,existsSync} from "node:fs";
import {dirname,resolve,relative,sep} from "node:path";
import {fileURLToPath} from "node:url";
import * as shaders from "../src/jarvis/presentation/web/assets/rendering/shaders.js";
const root=fileURLToPath(new URL("../src/jarvis/presentation/web/assets/",import.meta.url));
function files(folder){return readdirSync(folder).flatMap(name=>{const p=resolve(folder,name);return statSync(p).isDirectory()?files(p):[p]});}
let links=0;
for(const path of files(root).filter(p=>p.endsWith(".js"))){
 const text=readFileSync(path,"utf8");
 for(const match of text.matchAll(/(?:from\s*|import\s*\(\s*)["'](\.[^"']+)["']/g)){
  const target=resolve(dirname(path),match[1]);
  assert(!relative(root,target).startsWith(".."),`Import escapes assets: ${relative(root,path)}`);
  assert(existsSync(target),`Missing module ${match[1]} in ${relative(root,path)}`);links++;
 }
 const module=relative(root,path).split(sep).join("/");
 if(module.startsWith("core/")||module==="rendering/city_geometry.js"||module==="features/navigation/routes.js"){
  assert(!/from\s*["'][^"']*(?:rendering\/energy|rendering\/city\.js|ui\/|app\.js)/.test(text),`Upward import in ${module}`);
 }
}
for(const [name,source]of Object.entries(shaders)){
 assert.equal(typeof source,"string",name);
 assert(!/^export /m.test(source),`JavaScript export leaked into GLSL: ${name}`);
 assert(source.trim().length>0,name);
}
assert(readFileSync(resolve(root,"index.html"),"utf8").includes('type="module" src="/app.js"'));
console.log(`Frontend module imports, pure geometry boundaries and shader exports passed (${links} links).`);