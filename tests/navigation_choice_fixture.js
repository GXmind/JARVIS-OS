(()=>{
 const n=window.__navigation;
 n.AMap.PlaceSearch=class{
  search(keyword,callback){
   const origin={id:"origin",name:keyword,cityname:"苏州市",address:"测试起点",location:[120.60,31.31]};
   const parks=[
    {id:"park-a",name:"同名公园",cityname:"苏州市",type:"风景名胜;公园",address:"测试公园甲",location:[120.61,31.32]},
    {id:"park-b",name:"同名公园",cityname:"苏州市",type:"风景名胜;公园",address:"测试公园乙",location:[120.615,31.33]}
   ];
   callback("complete",{poiList:{pois:keyword==="同名公园"?parks:[origin]}});
  }
 };
 void n.open({id:889,action:"route",origin:"测试起点",destination:"同名公园",city:"苏州",mode:"compare"});
 return true;
})()
