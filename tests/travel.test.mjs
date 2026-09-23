import test from "node:test";
import assert from "node:assert/strict";
import {compareTravel,validateTravel,validateRoutes,renderTravel,exampleComparison,createRouteFeed,locate,probeRouting,destinations} from "../dashboard/travel.mjs";

const at="2026-09-14T17:00:00Z", now=Date.parse(at);
const facilities=[{slug:"a",display_name:"Example A"},{slug:"b",display_name:"Example B"}];
function fixture() {
  const context={schema_version:1,method_version:"travel-wait-v1",metric:"CV_ED_Wait",generated_at:at,
    recommendations_enabled:false,policy:{route_ttl_seconds:300,context_ttl_seconds:7200,meaningful_minutes:10},
    facilities:facilities.map(f=>({...f,eligibility:{adult:null,child:"Unverified"},arrival:"entrance",movement:[15,30,60,120].map(h=>
      ({horizon_minutes:h,pairs:500,days:10,absolute_change_p90:5}))}))};
  const routes={schema_version:2,provider:"tomtom",traffic_mode:"live",generated_at:at,ttl_seconds:300,age_group:"adult",
    routes:[{slug:"a",status:"ok",seconds:720,meters:4000,traffic_delay_seconds:60},
      {slug:"b",status:"ok",seconds:1530,meters:10000,traffic_delay_seconds:null}]};
  const live={refreshFailed:false,artifact:{generated_at:at,freshness:{stale_after_seconds:1800},
    facilities:facilities.map((f,i)=>({slug:f.slug,last_success:{wait_minutes:i ? 35 : 80,observed_at:at},last_attempt:{state:"success"}}))}};
  return {context,routes,live,now};
}

test("component arithmetic keeps seconds, closest uses road time, and recommendations stay off",()=>{
  const input=fixture();validateTravel(input.context,facilities);
  const result=compareTravel(input), b=result.rows[1];
  assert.equal(result.closest,"a");assert.equal(result.rows[0].total,92);
  assert.equal(b.drive,25.5);assert.equal(b.total,60.5);assert.equal(b.extraDrive,13.5);assert.equal(b.difference,31.5);
  assert.equal(b.screen,20);assert.equal(b.clearsMovementScreen,true);
  assert.equal(result.preferred,null);assert.match(result.message,/live traffic where available/);
  assert.equal(result.rows[0].trafficDelay,60);assert.equal(b.trafficDelay,null);
  input.live.artifact.facilities[1].last_success.wait_minutes=0;
  assert.equal(compareTravel(input).rows[1].total,25.5);
});

test("missing closest wait never rebases closest; partial routes withhold all differences",()=>{
  const input=fixture();input.live.artifact.facilities[0].last_success=null;
  let result=compareTravel(input);assert.equal(result.closest,"a");
  assert.equal(result.rows[0].total,null);assert.equal(result.rows[1].difference,null);
  input.routes.routes[0]={slug:"a",status:"unavailable",seconds:null,meters:null,traffic_delay_seconds:null};
  result=compareTravel(input);assert.equal(result.closest,null);
  assert.ok(result.rows.every(r=>r.difference===null));assert.match(result.message,/withheld/);
});

test("stale or failed waits and routes, future clocks, and context expiry suppress comparisons",()=>{
  for(const patch of [i=>i.live.refreshFailed=true,i=>i.live.artifact.facilities.forEach(f=>f.last_attempt.state="failed"),
    i=>i.live.artifact.generated_at=new Date(now-1800000).toISOString()]) {
    const input=fixture();patch(input);assert.ok(compareTravel(input).rows.every(r=>r.total===null));
  }
  for(const offset of [300000,-1]) { const input=fixture();input.now+=offset;assert.equal(compareTravel(input).rows.length,0); }
  const input=fixture();input.context.generated_at=new Date(now-7200000).toISOString();assert.equal(compareTravel(input).rows.length,0);
  assert.equal(compareTravel({...fixture(),contextFailed:true}).rows.length,0);
});

test("suitability, wrong matrix coverage, unsupported horizons and uncertain differences",()=>{
  const input=fixture();input.context.facilities[1].eligibility.adult="Unverified";
  assert.equal(compareTravel(input).rows.length,0);
  const sparse=fixture();sparse.context.facilities[1].movement.forEach(m=>m.absolute_change_p90=null);
  assert.equal(compareTravel(sparse).rows[1].screen,null);
  const long=fixture();long.routes.routes[1].seconds=121*60;assert.equal(compareTravel(long).rows[1].movement,null);
  const weak=fixture();weak.live.artifact.facilities[1].last_success.wait_minutes=70;
  assert.equal(compareTravel(weak).rows[1].clearsMovementScreen,false);
  const empty=fixture();empty.context.facilities=[];empty.routes.routes=[];assert.equal(compareTravel(empty).rows.length,0);
});

test("invalid contracts fail closed, including enabled recommendations and fake traffic",()=>{
  const i=fixture();i.context.recommendations_enabled=true;assert.throws(()=>validateTravel(i.context,facilities));
  const j=fixture();j.routes.traffic_mode="historical";assert.throws(()=>validateRoutes(j.routes,facilities,"adult"));
  const k=fixture();k.routes.routes[0].seconds=-1;assert.throws(()=>validateRoutes(k.routes,facilities,"adult"));
  const l=fixture();l.context.facilities[0].movement[0].days=1;assert.throws(()=>validateTravel(l.context,facilities));
});

test("accessible bars escape names and label illustrative data without patient savings",()=>{
  const input=fixture();input.context.facilities[0].display_name="<img onerror=bad>";
  const html=renderTravel(compareTravel(input));assert.ok(!html.includes("<img"));assert.match(html,/role="img" aria-label=/);
  const example=renderTravel(exampleComparison(),true);assert.match(example,/Illustrative example · fictional/);
  assert.match(example,/32 min lower estimate/);assert.ok(!example.includes("recommended"));
});

test("origins use POST only; clearing discards in-flight responses and failure clears results",async()=>{
  let resolve,options,url;const states=[];
  const feed=createRouteFeed({onChange:s=>states.push(s),fetcher:(u,o)=>{url=u;options=o;return new Promise(r=>resolve=r);}});
  const i=fixture();const pending=feed.request({latitude:35,longitude:-90},i.context,"adult");
  assert.equal(url,"/api/routes");assert.equal(options.method,"POST");assert.equal(options.cache,"no-store");
  assert.deepEqual(JSON.parse(options.body),{latitude:35,longitude:-90,age_group:"adult"});
  feed.clear();resolve({ok:true,json:async()=>i.routes});await pending;assert.equal(states.length,0);
  const failure=createRouteFeed({onChange:s=>states.push(s),fetcher:async()=>({ok:false})});
  await failure.request({latitude:35,longitude:-90},i.context,"adult");assert.equal(states.at(-1).routes,null);
});

test("denied and unavailable opt-in geolocation offer manual input; success returns coordinates",async()=>{
  await assert.rejects(locate(null),/enter coordinates/);
  await assert.rejects(locate({getCurrentPosition:(ok,fail)=>fail({code:1})}),/denied/);
  assert.deepEqual(await locate({getCurrentPosition:(ok,fail,options)=>{assert.equal(options.maximumAge,0);ok({coords:{latitude:35,longitude:-90}});}}),
    {latitude:35,longitude:-90});
});

test("TomTom traffic delay is informational and old provider contracts are rejected",()=>{
  const input=fixture();
  assert.equal(compareTravel(input).rows[0].total,92); // 12 drive already includes 1 min delay.
  input.routes.routes[0].traffic_delay_seconds=0;
  assert.equal(compareTravel(input).rows[0].trafficDelay,0);
  input.routes.routes[0].traffic_delay_seconds=721;
  assert.throws(()=>validateRoutes(input.routes,facilities,"adult"));
  const old=fixture();old.routes.schema_version=1;old.routes.provider="fossgis_osrm";
  assert.throws(()=>validateRoutes(old.routes,facilities,"adult"));
});

test("routing setup and quota errors remain distinct; raw provider messages never reach the page",async()=>{
  for(const [code,message] of [["routing_not_configured",/not available yet/],
    ["request_budget_exhausted",/allowance reached/],["provider_limit_reached",/provider limit/],
    ["__proto__",/Road estimates unavailable/]]) {
    let result;
    const feed=createRouteFeed({fetcher:async()=>({ok:false,json:async()=>({error:code,message:"secret-key-and-origin"})}),onChange:r=>result=r});
    await feed.request({latitude:35,longitude:-90},fixture().context,"adult");
    assert.equal(result.routes,null);assert.match(result.error,message);
    assert.ok(!result.error.includes("secret-key"));
  }
});

test("routing probe enables Compare only for an explicit gateway confirmation",async()=>{
  const reply=(ok,body)=>async()=>({ok,json:async()=>body});
  assert.equal(await probeRouting(reply(true,{schema_version:1,available:true})),true);
  assert.equal(await probeRouting(reply(false,{})),false, "static S3 returns 403/404");
  assert.equal(await probeRouting(reply(true,{schema_version:1,available:"yes"})),false);
  assert.equal(await probeRouting(reply(true,null)),false);
  assert.equal(await probeRouting(async()=>{throw Error("offline");}),false);
  let requested=null;
  await probeRouting(async(url,options)=>{requested={url,options};return {ok:false};});
  assert.equal(requested.url,"/api/routes/status");
  assert.equal(requested.options.method,undefined, "the probe never posts an origin");
});

test("campus-center arrivals are labeled everywhere and never called verified entrances",()=>{
  const input=fixture();input.context.facilities[1].arrival="campus";
  validateTravel(input.context,facilities);
  const result=compareTravel(input);
  assert.deepEqual(result.rows.map(r=>r.arrival),["entrance","campus"]);
  const html=renderTravel(result);
  assert.equal((html.match(/ER entrance unconfirmed/g) ?? []).length,2, "visible note and bar label, only for the campus row");
  assert.match(html,/Drive to campus center/);
  assert.equal(destinations(input.context.facilities),"2 eligible destinations · 1 to campus center, ER entrance unconfirmed");
  input.context.facilities[0].arrival="campus";
  assert.match(destinations(input.context.facilities),/all to campus center/);
  assert.equal(destinations([{arrival:"entrance"}]),"1 eligible destination");
  for(const bad of ["unknown",undefined]) {
    const c=fixture();c.context.facilities[0].arrival=bad;assert.throws(()=>validateTravel(c.context,facilities));
  }
  const noPoint=fixture();noPoint.context.facilities[0].arrival=null;
  assert.throws(()=>validateTravel(noPoint.context,facilities), "an eligible destination needs an arrival point");
});
