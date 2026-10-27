/* Resolve and verify a place before any routing API receives its coordinates. */
export function placePoint(value){
 const x=typeof value?.getLng==="function"?value.getLng():value?.lng??value?.[0];
 const y=typeof value?.getLat==="function"?value.getLat():value?.lat??value?.[1];
 return x!=null&&y!=null&&Number.isFinite(Number(x))&&Number.isFinite(Number(y))&&Math.abs(Number(x))<=180&&Math.abs(Number(y))<=90?[Number(x),Number(y)]:null;
}
function fold(text){
 return String(text||"").replace(/[一二三四五六七八九]/g,c=>"一二三四五六七八九".indexOf(c)+1)
  .replace(/[\s（）()·\-]/g,"").replace(/山风景名胜区|山风景区|风景名胜区|风景园区|风景区|景区/g,"");
}
export function rankPlaces(query,rows,city){
 const cityName=String(city||"").replace(/市$/,"");
 const normalized=rows.map(p=>{
  const location=placePoint(p.location);
  const pcity=String(p.cityname||p.city||"").replace(/市$/,"");
  if(!location||pcity&&cityName&&pcity!==cityName)return null;
  let q=String(query).trim();
  for(const prefix of [p.pname,p.cityname,p.adname])if(prefix&&q.startsWith(prefix))q=q.slice(prefix.length);
  const key=fold(q),name=fold(p.name),address=fold(p.address);
  let score=name===key?1000:name.startsWith(key)&&key.length>=2?620:name.includes(key)&&key.length>=2?540:0;
  if(address.includes(key)&&key.length>=5)score=Math.max(score,650);
  if(/景区|风景|公园/.test(query)){
   if(String(p.type).startsWith("11"))score+=70;
   if(/停车场|游客中心|检票|咖啡|驿站|出入口/.test(p.name))score-=170;
  }else if(/家园|小区|住宅/.test(query)){
   if(String(p.type).startsWith("12"))score+=50;
   if(/停车|公交站|快递|幼儿园|出入口/.test(p.name))score-=170;
  }
  return {id:String(p.id||""),name:String(p.name||query),address:String(p.address||""),
   city:String(p.cityname||p.city||city),area:String(p.adname||""),location,score};
 }).filter(p=>p&&p.score>=450).sort((a,b)=>b.score-a.score);
 const unique=[];for(const p of normalized)if(!unique.some(q=>q.id&&q.id===p.id))unique.push(p);
 return unique;
}
export function confidentPlace(candidates){
 return candidates[0]&&(!candidates[1]||candidates[0].score-candidates[1].score>=100)?candidates[0]:null;
}
export function groundDistance(a,b){
 const rad=Math.PI/180,dlat=(b[1]-a[1])*rad,dlng=(b[0]-a[0])*rad;
 const h=Math.sin(dlat/2)**2+Math.cos(a[1]*rad)*Math.cos(b[1]*rad)*Math.sin(dlng/2)**2;
 return 6371000*2*Math.asin(Math.min(1,Math.sqrt(h)));
}