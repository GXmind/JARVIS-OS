(async()=>{
 const controller=window.__navigation;controller.close();
 const path=[[120.60,31.31],[120.61,31.31],[120.61,31.32]];
 class FixturePlanner{
  search(origin,destination,callback){if(!Array.isArray(origin)||!Array.isArray(destination))throw new Error("Planner requires confirmed coordinates");origin[0]=999;setTimeout(()=>callback("complete",{routes:[{distance:1800,time:360,steps:[{path,road:"测试道路",instruction:"Synthetic test geometry"}]}]}),15);}
 }
 class FixtureTransfer{
  search(origin,destination,callback){if(origin[0]!==120.60||destination[0]!==120.61)throw new Error("Planners share mutable endpoints");setTimeout(()=>callback("complete",{taxi_cost:18,plans:[{distance:2100,time:720,path,segments:[{instruction:"步行至测试站"},{instruction:"乘坐测试地铁"}]}]}),15);}
 }
 class FixturePlaceSearch{
  search(keyword,callback){
   callback("complete",{poiList:{pois:[{id:keyword,name:keyword,cityname:"苏州市",adname:"姑苏区",address:"测试地址",
    location:keyword.includes("起点")?{lng:120.60,lat:31.31}:{lng:120.61,lat:31.32}}]}});
  }
 }
 window.AMap={PlaceSearch:FixturePlaceSearch,Driving:FixturePlanner,Walking:FixturePlanner,Transfer:FixtureTransfer,
  Map:class{constructor(){throw new Error("Flat map constructor must not be used")}},
  plugin:(_plugins,ready)=>ready()};
 const originalApi=controller.api;
 controller.api=async (name,body)=>name==="map/config"?{configured:true,key:"TEST_ONLY",city:"苏州",default_origin:""}:
  name==="city/context"?{status:"synthetic-fixture",buildings:[
   {footprint:[[120.602,31.312],[120.603,31.312],[120.603,31.313],[120.602,31.313],[120.602,31.312]],height:36},
   {footprint:[[120.606,31.315],[120.608,31.315],[120.608,31.316],[120.606,31.316],[120.606,31.315]],height:58}
  ],roads:[{path}]}:name==="navigation/result"?{}:originalApi(name,body);
 const route={id:888,action:"route",origin:"测试起点",destination:"测试终点",city:"苏州",mode:"compare"};
 await Promise.all([controller.open(route),controller.open(route)]);
 return true;
})()