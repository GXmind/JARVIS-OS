export function createClient(TOKEN){
async function api(path,body){
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),path==="city/context"?45000:15000);
 try{
  const response=await fetch("/api/"+path,{method:body===undefined?"GET":"POST",signal:controller.signal,
   headers:{"X-Jarvis-Token":TOKEN,...(body===undefined?{}:{"Content-Type":"application/json"})},
   ...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||"本机服务暂不可用");
  return data;
 }catch(error){
  if(error.name==="AbortError")throw new Error(path==="city/context"?"城市数据加载超时":"本机请求超时，请重试");
  throw error;
 }finally{clearTimeout(timer);}
}
return api;
}
