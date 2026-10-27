import assert from "node:assert/strict";
import {rankPlaces,confidentPlace,placePoint,groundDistance} from "../src/jarvis/space_ui/places.js";
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