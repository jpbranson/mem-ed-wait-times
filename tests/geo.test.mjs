import test from "node:test";
import assert from "node:assert/strict";
import {binHeatmap, renderHeatmap} from "../dashboard/heatmap.mjs";
import {glyphs, markerState, mountGeo, resolveIndex, snapshot} from "../dashboard/geo.mjs";

const expected=[{slug:"a",display_name:"Hospital <A>",short_name:"A",campus:{latitude:35.1,longitude:-90}},
  {slug:"b",display_name:"Hospital B",campus:{latitude:34.2,longitude:-88.7}},{slug:"c",display_name:"No campus",campus:null}];
const generated="2026-09-14T16:05:00Z", end=Date.parse("2026-09-14T17:00:00Z"), hour=3600000;
const point=(at,value,delta)=>[new Date(at).toISOString(),value,delta===null?null:value-delta,null,null,delta,null,0,0,"weekday_weekend"];
const context=(at=generated)=>({generated_at:at,facilities:[
  {slug:"a",history:[point(end-2*hour,90,35),point(end-hour+60000,20,-25)]},
  {slug:"b",history:[point(end-hour,50,null)]},{slug:"c",history:[point(end-hour,10,0)]}]});

class Element extends EventTarget {
  value="";textContent="";innerHTML="";disabled=false;max="";attributes={};
  setAttribute(key,value) {this.attributes[key]=value;}
  fire(type) {this.dispatchEvent(new Event(type));}
}
const areas=[{key:"all",label:"All hospitals",slugs:["a","b","c"]},{key:"pair",label:"A & <B>",slugs:["a","b"]}];
function fixture({createMap}={}) {
  const elements=new Map(), updates=[], periods=[], timers=[], fits=[];
  const root={querySelector(selector){if(!elements.has(selector)) elements.set(selector,new Element());return elements.get(selector);}};
  const map={update(entries,focus){updates.push({entries,focus});},fit(slugs){fits.push(slugs);}};
  const geo=mountGeo(root,{expected,areas,Observer:null,onPeriod:index=>periods.push(index),
    createMap:createMap ?? (async()=>map),every:(fn)=>{timers.push(fn);return timers.length;},cancel:id=>{timers[id-1]=null;}});
  return {geo,get:s=>root.querySelector(s),updates,periods,timers,fits};
}
const settled=()=>new Promise(resolve=>setImmediate(resolve));

test("marker states carry direction by glyph as well as color",()=>{
  assert.deepEqual(markerState({readings:0,delta:null}),{kind:"empty",band:"empty",glyph:"–",text:"no reading"});
  assert.equal(markerState({readings:2,delta:null}).kind,"unsupported");
  assert.deepEqual([35,11,10,-10,-11,-45].map(d=>markerState({readings:1,delta:d}).glyph),
    [glyphs.above,glyphs.above,glyphs.near,glyphs.near,glyphs.below,glyphs.below]);
  assert.equal(markerState({readings:1,delta:35}).band,"above-2");
  assert.match(markerState({readings:1,delta:-25}).text,/-25 min from usual/);
});

test("the map snapshot matches the heatmap column and skips hospitals without a campus",()=>{
  const model=binHeatmap(context(),expected,168);
  const entries=snapshot(model,166,expected);
  assert.deepEqual(entries.map(e=>e.slug),["a","b"]);
  assert.deepEqual([entries[0].latitude,entries[0].longitude],[35.1,-90]);
  assert.equal(entries[0].kind,"above");
  assert.equal(entries[1].kind,"empty");
  assert.match(entries[0].label,/^Hospital <A>: median \+35 min from usual, Sep 14, /);
  const last=snapshot(model,167,expected);
  assert.deepEqual(last.map(e=>e.kind),["below","unsupported"]);
});

test("the replayed period survives rebuilds while it stays in the window",()=>{
  const model=binHeatmap(context(),expected,168);
  assert.equal(resolveIndex(model),167);
  assert.equal(resolveIndex(model,{start:model.start+100*hour,follow:false}),100);
  assert.equal(resolveIndex(model,{start:model.start-hour,follow:false}),167);
  assert.equal(resolveIndex(model,{start:model.start+100*hour,follow:true}),167);
});

test("the heatmap outlines the replayed column",()=>{
  const model=binHeatmap(context(),expected,168);
  const {svg,layout}=renderHeatmap(model,{width:900,marker:166});
  const x=(layout.labelWidth+166*layout.cellWidth).toFixed(2);
  assert.match(svg,new RegExp(`<rect class="heat-replay" x="${x}"[^>]*visibility="visible"`));
  assert.match(renderHeatmap(model,{width:900}).svg,/class="heat-replay"[^>]*visibility="hidden"/);
});

test("replay controls follow the latest period, step, play and reset with the window",async()=>{
  const f=fixture();
  await settled();
  assert.equal(f.get(".geo-slider").disabled,true);
  assert.equal(f.get(".geo-period").textContent,"No history to replay");
  f.geo.render(context(),168,"a");
  assert.equal(f.get(".geo-slider").max,"167");
  assert.equal(f.get(".geo-slider").value,"167");
  assert.match(f.get(".geo-period").textContent,/latest$/);
  assert.equal(f.get(".geo-latest").disabled,true);
  assert.equal(f.periods.at(-1),167);
  assert.equal(f.updates.at(-1).focus,"a");
  assert.deepEqual(f.updates.at(-1).entries.map(e=>e.kind),["below","unsupported"]);
  f.get(".geo-slider").value="166";
  f.get(".geo-slider").fire("input");
  assert.equal(f.periods.at(-1),166);
  assert.doesNotMatch(f.get(".geo-period").textContent,/latest/);
  assert.equal(f.get(".geo-slider").attributes["aria-valuetext"],f.get(".geo-period").textContent);
  assert.equal(f.get(".geo-latest").disabled,false);
  assert.equal(f.updates.at(-1).entries[0].kind,"above");
  // An hour later the same period is one column earlier.
  f.geo.render(context("2026-09-14T17:05:00Z"),168,"a");
  assert.equal(f.get(".geo-slider").value,"165");
  f.get(".geo-latest").fire("click");
  assert.equal(f.get(".geo-slider").value,"167");
  // Play from the latest period restarts at the beginning and advances one period per tick.
  f.get(".geo-play").fire("click");
  assert.equal(f.get(".geo-slider").value,"0");
  assert.equal(f.get(".geo-play").attributes["aria-pressed"],"true");
  f.timers.at(-1)();
  assert.equal(f.get(".geo-slider").value,"1");
  f.get(".geo-slider").value="10";
  f.get(".geo-slider").fire("input");  // Manual stepping stops playback.
  assert.equal(f.get(".geo-play").attributes["aria-pressed"],"false");
  assert.equal(f.timers.at(-1),null);
  // Switching to 24 hours starts at that window's latest period.
  f.geo.render(context(),24,"a");
  assert.equal(f.get(".geo-slider").max,"95");
  assert.equal(f.get(".geo-slider").value,"95");
  f.geo.render(null,24,"a");
  assert.equal(f.get(".geo-slider").disabled,true);
  assert.equal(f.periods.at(-1),null);
});

test("map views reuse the area groups and frame only their hospitals",async()=>{
  const f=fixture();
  await settled();
  assert.equal(f.get(".geo-area").innerHTML,'<option value="all">All hospitals</option><option value="pair">A &amp; &lt;B&gt;</option>');
  assert.deepEqual(f.fits,[], "the default view keeps the initial framing");
  f.get(".geo-area").value="pair";
  f.get(".geo-area").fire("change");
  assert.deepEqual(f.fits,[["a","b"]]);
});

test("a map failure leaves the heatmap as the fallback",async()=>{
  const f=fixture({createMap:async()=>{throw Error("no WebGL");}});
  await settled();
  assert.match(f.get(".geo-status").textContent,/Map unavailable/);
  f.geo.render(context(),168,"a");
  assert.equal(f.get(".geo-slider").disabled,false);
});
