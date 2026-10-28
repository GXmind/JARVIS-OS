import assert from "node:assert/strict";
import {rankPlaces,confidentPlace,placePoint,groundDistance} from "../src/jarvis/presentation/web/assets/features/navigation/places.js";
const rows=[
 {id:"wrong",name:"外市测试咖啡店",cityname:"上海市",type:"050000",location:{lng:121.497583,lat:31.226349}},
 {id:"park",name:"虎丘山风景区",cityname:"苏州市",adname:"姑苏区",address:"山塘街898号",type:"110000",location:{lng:120.580016,lat:31.334584}},
 {id:"tower",name:"虎丘塔",cityname:"苏州市",adname:"姑苏区",type:"110000",location:{lng:120.580553,lat:31.335827}}
];
const ranked=rankPlaces("虎丘风景园区",rows,"苏州");
assert.equal(confidentPlace(ranked).id,"park");
assert.ok(!ranked.some(p=>p.id==="wrong"),"Out-of-city coffee POI must never become the scenic destination");
assert.equal(placePoint({lng:null,lat:31}),null);
assert.equal(confidentPlace([{id:"a",score:1000},{id:"b",score:1000}]),null,"Ambiguous POIs require a choice");
assert.ok(groundDistance([120.75,31.25],[120.580016,31.334584])>18000);
assert.ok(groundDistance([120.75,31.25],[120.580016,31.334584])<22000);
console.log("Local scenic POI ranking, foreign-place rejection, ambiguity and coordinate distance passed.");
const garden=[
 {id:"scenic",name:"拙政园",cityname:"苏州市",adname:"姑苏区",address:"东北街178号",type:"风景名胜;风景名胜;国家级景点",location:[120.629211,31.324194]},
 {id:"label",name:"拙政园",cityname:"苏州市",adname:"姑苏区",address:"姑苏区",type:"地名地址信息;热点地名;热点地名",location:[120.628659,31.324]},
 {id:"ticket",name:"拙政园东售票处",cityname:"苏州市",type:"生活服务;售票处",location:[120.630762,31.323426]}
];
assert.equal(confidentPlace(rankPlaces("拙政园",garden,"苏州")).id,"scenic","Localized SDK categories must prefer a precise scenic POI over a generic geographic label");
const sameNameParks=garden.filter(p=>p.id==="scenic").flatMap(p=>[p,{...p,id:"different-park",location:[120.68,31.35]}]);
assert.equal(confidentPlace(rankPlaces("拙政园",sameNameParks,"苏州")),null,"Two real same-name scenic POIs must still require a choice");
assert.equal(confidentPlace(rankPlaces("拙政园",garden.map(p=>({...p,type:"",typecode:p.id==="scenic"?"110200":p.id==="label"?"190000":"070300"})),"苏州")).id,"scenic");
console.log("Actual Chinese SDK POI categories, numeric typecode and genuine scenic ambiguity passed.");
