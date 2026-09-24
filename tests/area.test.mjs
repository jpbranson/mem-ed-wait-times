import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {binArea, currentArea, pointState, renderAreaChart, renderAreaNow, validateAreas} from "../dashboard/area.mjs";
import {stabilityGraphic, validateContext} from "../dashboard/comparisons.mjs";

const policy=JSON.parse(readFileSync(new URL("../docs/m1-replay-evidence.json",import.meta.url))).selected_policy;
const expected=[{slug:"a",display_name:"Hospital <A>",short_name:"A"},{slug:"b",display_name:"Hospital B",short_name:"B"},{slug:"c",display_name:"Hospital C",short_name:"C"}];
const areas=[{key:"all",label:"All hospitals",basis:"All configured facilities",slugs:["a","b","c"]},
  {key:"near-a",label:"A / B",basis:"Campus centers linked within 50 km (straight line)",slugs:["a","b"]}];
const at="2026-09-14T16:05:00Z", now=Date.parse(at), hour=3600000, end=Date.parse("2026-09-14T17:00:00Z");
// [time, value, median, low, high, delta, percentile, days, coverage, group]
const point=(time,delta,percentile)=>[new Date(time).toISOString(),20+(delta ?? 0),delta===null?null:20,delta===null?null:15,delta===null?null:25,delta,percentile,delta===null?0:20,1,"weekday_weekend"];

test("area groups must cover known slugs without duplicates, starting with all hospitals",()=>{
  assert.equal(validateAreas(areas,expected),areas);
  for(const bad of [[areas[1]],[{...areas[0],slugs:["a","b"]}],[areas[0],{...areas[1],slugs:["a","z"]}],
    [areas[0],{...areas[1],slugs:["a","a"]}],[areas[0],{...areas[1],key:"all"}]]) assert.throws(()=>validateAreas(bad,expected));
});

test("history points follow the focus summary's outer-10%-plus-10-minute rule",()=>{
  assert.equal(pointState(point(0,12,95),policy),"above");
  assert.equal(pointState(point(0,9,99),policy),"near", "percentile alone is not enough");
  assert.equal(pointState(point(0,30,80),policy),"near", "distance alone is not enough");
  assert.equal(pointState(point(0,-15,5),policy),"below");
  assert.equal(pointState(point(0,null,null),policy),"no_range");
});

test("periods use each hospital's latest reading and count only hospitals with a usual range",()=>{
  const context={generated_at:at,policy,facilities:[
    {slug:"a",history:[point(end-2*hour,-15,5),point(end-2*hour+30*60000,15,95),point(end-hour,15,95)]},
    {slug:"b",history:[point(end-2*hour+15*60000,null,null),point(end-hour+60000,-12,4)]},
    {slug:"c",history:[point(end-hour,40,99)]}]};
  const model=binArea(context,areas[1],168), bins=model.bins;
  assert.equal(model.columns,168); assert.equal(model.end,end);
  assert.deepEqual([bins[166].reporting,bins[166].compared,bins[166].above],[2,1,["a"]], "latest reading replaces the earlier below-usual one");
  assert.deepEqual([bins[167].above,bins[167].below],[["a"],["b"]]);
  assert.equal(bins.filter(b=>b.reporting).length,2, "hospital c is outside the area");
  assert.deepEqual(model.perFacility.get("b"),{above:0,below:1,compared:1,reporting:2});
  assert.equal(model.typicalAbove,1); assert.equal(model.periodsWithAbove,2);
  const {svg,table}=renderAreaChart(model,new Map([["a","A"],["b","B"]]),{width:900,full:new Map([["a","Hospital <A>"],["b","Hospital B"]])});
  assert.equal((svg.match(/class="area-above"/g) ?? []).length,2);
  assert.equal((svg.match(/class="area-below"/g) ?? []).length,1);
  assert.match(svg,/1 above usual \(A\); 1 below \(B\); 2 of 2 with a usual range/);
  assert.match(table,/Hospital &lt;A&gt;/); assert.doesNotMatch(table,/<A>/);
});

function live(values) {
  return {refreshFailed:false,artifact:{schema_version:1,generated_at:at,
    freshness:{stale_after_seconds:1800,refresh_seconds:60,request_timeout_seconds:10,expected_collection_seconds:900},
    facilities:Object.entries(values).map(([slug,wait])=>({slug,reporting_state:"reporting",last_attempt:{state:"success"},
      last_success:wait===null ? null : {facility:slug,metric:"CV_ED_Wait",wait_minutes:wait,observed_at:at,batch_id:at,latency_ms:1}}))}};
}
function context(generated=at) {
  const model=(state="supported")=>({state,group:"weekday_weekend",hour_radius:1,support:{days:20,eligible_days:20,samples:200,observed_slots:200,expected_slots:200,coverage:1},
    reference_start:"2026-08-17",reference_end_exclusive:"2026-09-14",...(state==="supported" ?
      {median:20,low:15,high:25,distribution:[[10,20],[15,40],[20,80],[25,40],[30,20]]} : {median:null,low:null,high:null,distribution:[]})});
  return {generated_at:generated,valid_until:"2026-09-15T05:00:00Z",policy,facilities:[
    {slug:"a",models:{"2026-09-14":Array.from({length:24},()=>model())},history:[]},
    {slug:"b",models:{"2026-09-14":Array.from({length:24},()=>model())},history:[]},
    {slug:"c",models:{"2026-09-14":Array.from({length:24},()=>model("insufficient_history"))},history:[]}]};
}

test("current counts separate compared, unsupported and not-current hospitals, and pause without context",()=>{
  const current=currentArea(areas[0],{context:context(),live:live({a:45,b:5,c:30}),now});
  assert.deepEqual([current.above,current.below,current.compared,current.noRange,current.notCurrent],[1,1,2,1,0]);
  const html=renderAreaNow(current,new Map([["a","A <x>"],["b","B"]]));
  assert.match(html,/<strong>1<\/strong> above usual/); assert.match(html,/A &lt;x&gt;/); assert.match(html,/1 without a usual range/);
  const missing=currentArea(areas[0],{context:context(),live:live({a:45,b:null,c:30}),now});
  assert.deepEqual([missing.compared,missing.notCurrent],[1,1]);
  const stale=currentArea(areas[0],{context:context("2026-09-14T13:00:00Z"),live:live({a:45,b:5,c:30}),now});
  assert.equal(stale.paused,true); assert.equal(stale.above,0);
  assert.match(renderAreaNow(stale,new Map()),/Comparisons paused/);
});

const row=(horizon,median,p90,rise,fall,pairs=500)=>({horizon_minutes:horizon,pairs,days:20,median_abs_change:median,p90_abs_change:p90,rise_share:rise,fall_share:fall});
test("stability graphic shows median, 90th percentile and 10+ minute share; validation rejects inconsistent rows",()=>{
  const rows=[row(15,2,8,.03,.04),row(30,4,14,.1,.08),row(60,6,22,.2,.15),row(120,null,null,null,null,10)];
  const svg=stabilityGraphic(rows,300,10);
  assert.equal((svg.match(/class="stability-median"/g) ?? []).length,3);
  assert.match(svg,/>7%</); assert.match(svg,/>35%</); assert.match(svg,/Insufficient history/);
  assert.match(svg,/1 h: median 6, 90th percentile 22 minutes, 35% moved 10 or more/);
  assert.match(svg,/>10<\/text>/); assert.match(svg,/>22<\/text>/, "minute axis marks the threshold and largest whisker");
  assert.match(stabilityGraphic([row(15,null,null,null,null)]),/Typical movement unavailable/);
  const base={schema_version:1,method_version:"self-comparison-v1",metric:"CV_ED_Wait",local_timezone:"America/Chicago",...context(),
    valid_until:"2026-09-15T05:00:00Z",stability:{method_version:"wait-stability-v1"}};
  const withRows=rows=>({...structuredClone(base),facilities:base.facilities.map(f=>({...structuredClone(f),stability:rows}))});
  assert.doesNotThrow(()=>validateContext(withRows(rows),expected));
  assert.doesNotThrow(()=>validateContext({...structuredClone(base),stability:undefined},expected), "older artifacts without stability remain valid");
  for(const bad of [rows.slice(1),[row(15,9,8,.1,.1),...rows.slice(1)],[row(15,2,8,.7,.6),...rows.slice(1)],[row(15,2,8,.1,null),...rows.slice(1)]])
    assert.throws(()=>validateContext(withRows(bad),expected));
  assert.throws(()=>validateContext({...withRows(rows),stability:{method_version:"other"}},expected));
});
