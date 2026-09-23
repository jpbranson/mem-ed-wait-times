import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {locate,mountOriginPicker,readOrigin} from "../dashboard/origin.mjs";
import {mountTravel} from "../dashboard/travel.mjs";

class Element extends EventTarget {
  value="";textContent="";innerHTML="";disabled=false;hidden=false;attributes={};
  setAttribute(key,value) {this.attributes[key]=value;}
  reportValidity() {return true;}
  fire(type) {this.dispatchEvent(new Event(type,{cancelable:true}));}
}
function fixture() {
  const elements=new Map();
  const root={querySelector(selector){if(!elements.has(selector)) elements.set(selector,new Element());return elements.get(selector);}};
  const get=selector=>root.querySelector(selector),events=new EventTarget();
  let mapOptions,selected=null,resets=0;
  const map={setOrigin(p){selected=p;},clear(){selected=null;resets++;},getCenter:()=>({latitude:35.14,longitude:-89.97})};
  const options={Observer:null,eventTarget:events,geolocation:null,createMap:async value=>{mapOptions=value;return map;}};
  return {root,get,events,options,map,get mapOptions(){return mapOptions;},get selected(){return selected;},get resets(){return resets;}};
}
const settled=()=>new Promise(resolve=>setImmediate(resolve));

test("origin input preserves zero, rejects partial or out-of-range points",()=>{
  assert.deepEqual(readOrigin("0","0"),{latitude:0,longitude:0});
  for(const pair of [["","0"],["35"," "],["NaN","2"],["91","0"],["0","-181"]]) assert.equal(readOrigin(...pair),null);
});

test("location errors distinguish permission, timeout, insecure context, and invalid responses",async()=>{
  for(const [code,match] of [[1,/permission denied/],[2,/Location unavailable/],[3,/timed out/]]) {
    await assert.rejects(locate({getCurrentPosition:(ok,fail)=>fail({code})}),match);
  }
  let calls=0;
  await assert.rejects(locate({getCurrentPosition:()=>calls++},{secure:false}),/HTTPS or localhost/);
  assert.equal(calls,0);
  await assert.rejects(locate({getCurrentPosition:ok=>ok({coords:{latitude:NaN,longitude:0}})}),/unavailable/);
  await assert.rejects(locate({getCurrentPosition(){}},{timeoutMs:5}),/timed out/);
});

test("GPS works before age/context/destination validation; changes never send routes",async()=>{
  const f=fixture(),requests=[];let gps;
  f.options.geolocation={getCurrentPosition:ok=>{gps=ok;}};
  const travel=mountTravel(f.root,{expected:[],getLive:()=>({}),fetcher:async url=>{requests.push(url);throw Error('offline');},originOptions:f.options});
  await settled();
  assert.equal(f.get('.travel-location').disabled,false);
  assert.equal(f.get('[type=submit]').disabled,true);
  f.get('.travel-location').fire('click');
  assert.equal(f.get('.travel-location').disabled,true);
  assert.match(f.get('.origin-status').textContent,/browser/);
  assert.doesNotMatch(f.get('.travel-status').textContent,/Calculating/);
  gps({coords:{latitude:35.15,longitude:-90.05}});await settled();
  assert.equal(f.get('[name=latitude]').value,'35.150000');
  assert.deepEqual(f.selected,{latitude:35.15,longitude:-90.05});
  assert.equal(f.get('.travel-location').disabled,false);
  assert.deepEqual(requests,[]);
  await travel.refresh(); // Context failure must not disable selecting another origin.
  assert.equal(f.get('.travel-location').disabled,false);
  assert.equal(f.get('[type=submit]').disabled,true);
  assert.deepEqual(requests,['travel.json']);
});

test("map, keyboard center, manual input, and Clear synchronize one origin",async()=>{
  const f=fixture();let changes=0;
  const picker=mountOriginPicker(f.root,{...f.options,onChange:()=>changes++});await settled();
  f.mapOptions.onSelect({latitude:35.12345678,longitude:-90.12345678});
  assert.equal(f.get('[name=longitude]').value,'-90.123457');assert.equal(changes,1);
  assert.deepEqual(picker.value(),f.selected);
  f.get('.origin-center').fire('click');assert.deepEqual(picker.value(),f.map.getCenter());
  f.get('[name=latitude]').value='0';f.get('[name=longitude]').value='0';f.get('[name=latitude]').fire('input');
  assert.deepEqual(f.selected,{latitude:0,longitude:0});
  f.get('[name=latitude]').value='';f.get('[name=latitude]').fire('input');assert.equal(f.selected,null);
  f.get('.travel-clear').fire('click');assert.equal(picker.value(),null);assert.equal(f.resets,1);
});

test("only Compare sends the selected origin; editing cancels a pending route",async()=>{
  const f=fixture(),at=new Date().toISOString(),requests=[];let finishRoute,gps;
  const facility={slug:'a',display_name:'Synthetic hospital',eligibility:{adult:null,child:null},
    movement:[15,30,60,120].map(h=>({horizon_minutes:h,pairs:0,days:0,absolute_change_p90:null}))};
  const context={schema_version:1,method_version:'travel-wait-v1',metric:'CV_ED_Wait',generated_at:at,
    recommendations_enabled:false,policy:{route_ttl_seconds:300,context_ttl_seconds:7200,meaningful_minutes:10},facilities:[facility]};
  const travel=mountTravel(f.root,{expected:[facility],getLive:()=>({}),originOptions:{...f.options,geolocation:{getCurrentPosition:ok=>{gps=ok;}}},
    fetcher:async(url,options)=>{
      if(url==='travel.json') return {ok:true,json:async()=>context};
      requests.push(options);return new Promise(resolve=>finishRoute=resolve);
    }});
  f.get('[name=age_group]').value='adult';await travel.refresh();await settled();
  f.mapOptions.onSelect({latitude:35,longitude:-90});assert.equal(requests.length,0);
  assert.equal(f.get('[type=submit]').disabled,false);
  f.get('form').fire('submit');assert.equal(requests.length,1);
  assert.deepEqual(JSON.parse(requests[0].body),{latitude:35,longitude:-90,age_group:'adult'});
  f.mapOptions.onSelect({latitude:35.1,longitude:-90.1});assert.equal(requests[0].signal.aborted,true);
  finishRoute({ok:true,json:async()=>({schema_version:2,provider:'tomtom',traffic_mode:'live',generated_at:at,ttl_seconds:300,age_group:'adult',
    routes:[{slug:'a',status:'ok',seconds:60,meters:100,traffic_delay_seconds:0}]})});await settled();
  assert.doesNotMatch(f.get('.travel-chart').innerHTML,/travel-bar|Synthetic hospital/);
  f.get('.travel-location').fire('click');assert.equal(f.get('[type=submit]').disabled,true);
  gps({coords:{latitude:35.2,longitude:-90.2}});await settled();
  assert.equal(f.get('[type=submit]').disabled,false);assert.equal(requests.length,1);
});

test("late GPS cannot overwrite a map selection, manual edit, Clear, or page exit",async()=>{
  for(const action of ['map','manual','clear','pagehide']) {
    const f=fixture();let gps;
    const picker=mountOriginPicker(f.root,{...f.options,geolocation:{getCurrentPosition:ok=>{gps=ok;}}});await settled();
    f.get('.travel-location').fire('click');
    if(action==='map') f.mapOptions.onSelect({latitude:35,longitude:-89});
    if(action==='manual') {f.get('[name=latitude]').value='35';f.get('[name=longitude]').value='-89';f.get('[name=latitude]').fire('input');}
    if(action==='clear') f.get('.travel-clear').fire('click');
    if(action==='pagehide') f.events.dispatchEvent(new Event('pagehide'));
    const before=picker.value();gps({coords:{latitude:40,longitude:-80}});await settled();
    assert.deepEqual(picker.value(),before);assert.equal(f.get('.travel-location').disabled,false);
  }
});

test("a map loading late uses the latest origin; failure leaves GPS/manual input usable",async()=>{
  const f=fixture();let ready;
  const picker=mountOriginPicker(f.root,{...f.options,createMap:()=>new Promise(resolve=>ready=resolve)});
  f.get('[name=latitude]').value='35';f.get('[name=longitude]').value='-90';f.get('[name=latitude]').fire('input');
  picker.clear();ready(f.map);await settled();assert.equal(f.selected,null);
  const g=fixture();mountOriginPicker(g.root,{...g.options,createMap:async()=>{throw Error('WebGL unavailable');}});await settled();
  assert.equal(g.get('.travel-location').disabled,false);assert.equal(g.get('.origin-center').disabled,true);
  assert.match(g.get('.origin-map-status').textContent,/Map unavailable/);assert.equal(g.get('.origin-map-retry').hidden,false);
});

test("pinned map labels use Inter at 16 px or larger; map sources need no key",async()=>{
  const style=JSON.parse(await readFile(new URL('../dashboard/origin-map-style.json',import.meta.url),'utf8'));
  const labels=style.layers.filter(l=>l.layout?.['text-field']);assert.ok(labels.length>0);
  for(const layer of labels) {assert.deepEqual(layer.layout['text-font'],['Inter']);assert.ok(layer.layout['text-size']>=16);}
  assert.equal(style.glyphs,undefined);
  for(const source of Object.values(style.sources)) {
    for(const url of [source.url,...source.tiles??[]].filter(Boolean)) {
      assert.equal(new URL(url).hostname,'tiles.openfreemap.org');assert.equal(new URL(url).search,'');
    }
  }
});
