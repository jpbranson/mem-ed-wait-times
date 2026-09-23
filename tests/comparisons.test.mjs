import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import {readFileSync} from "node:fs";
import {compareReading,contextAvailable,localGroup,mergeLiveHistory,recentDirection,renderHistory,renderSummary,validateContext} from "../dashboard/comparisons.mjs";
import {createContextFeed} from "../dashboard/app.mjs";
import {facilityView,createFeed} from "../dashboard/latest.mjs";

const expected=[{slug:"memphis",display_name:"Baptist Memphis"}];
const at="2026-09-14T15:00:00Z", now=Date.parse(at);
const policy=JSON.parse(readFileSync(new URL("../docs/m1-replay-evidence.json",import.meta.url))).selected_policy;
function fixture() {
  const model={state:"supported",group:"weekday_weekend",hour_radius:1,
    support:{days:20,eligible_days:20,samples:240,observed_slots:240,expected_slots:240,coverage:1},
    reference_start:"2026-08-17",reference_end_exclusive:"2026-09-14",median:20,low:20,high:20,distribution:[[20,240]]};
  return {schema_version:1,method_version:"self-comparison-v1",metric:"CV_ED_Wait",generated_at:at,
    valid_until:"2026-09-15T05:00:00Z",local_timezone:"America/Chicago",policy,
    facilities:[{slug:"memphis",models:{"2026-09-14":Array.from({length:24},()=>structuredClone(model))},
      history:[75,60,45].map((m,i)=>[new Date(now-m*60000).toISOString(),10+i*10,20,20,20,-10+i*10,50,20,1,"weekday_weekend"])}]};
}
function latest(wait=40) {
  return {schema_version:1,metric:"CV_ED_Wait",generated_at:at,
    freshness:{stale_after_seconds:1800,refresh_seconds:60,request_timeout_seconds:10,expected_collection_seconds:900},
    facilities:[{slug:"memphis",reporting_state:"reporting",last_success:{facility:"memphis",metric:"CV_ED_Wait",wait_minutes:wait,observed_at:at,batch_id:at,latency_ms:1},
      last_attempt:{batch_id:at,attempted_at:at,state:"success",error_code:null}}]};
}

test("browser agrees with independent arithmetic, zeros and local-time grouping",()=>{
  const data=validateContext(fixture(),expected),entry=data.facilities[0];
  assert.deepEqual(localGroup("2026-09-14T00:00:00Z"),{day:"2026-09-13",hour:19});
  assert.equal(localGroup("2026-11-01T06:30:00Z").hour,1);
  assert.equal(localGroup("2026-11-01T07:30:00Z").hour,1);
  const result=compareReading(entry,at,40,policy);
  assert.equal(result.delta,20); assert.equal(result.percentile,100); assert.equal(result.state,"above_usual");
  assert.equal(compareReading(entry,at,20,policy).percentile,50);
  assert.equal(compareReading(entry,at,25,policy).state,"no_large_departure");
  assert.equal(compareReading(entry,at,0,policy).delta,-20);
  assert.deepEqual(recentDirection(entry.history,at,40,policy),{state:"rising",delta:20,samples:3});
  assert.equal(recentDirection([entry.history[0],entry.history[2]],at,40,policy).state,"insufficient_recent_history");
  const retries=[{observed_at:at,wait_minutes:40},{observed_at:'2026-09-14T15:01:00Z',wait_minutes:50}];
  const merged=mergeLiveHistory(entry,retries,policy);
  assert.equal(merged.length,4,"live retries cannot inflate cadence support");
  assert.equal(merged.at(-1)[1],50);
});

test("new live reading gets context without rebuilding history; stale or failed reads pause comparisons",async t=>{
  let live=latest(), context=fixture(), failLive=false, failContext=false;
  const server=http.createServer((req,res)=>{
    const isLive=req.url==="/latest.json";
    res.writeHead((isLive?failLive:failContext)?503:200,{"Content-Type":"application/json"});
    res.end(JSON.stringify(isLive?live:context));
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  t.after(()=>{server.closeAllConnections();server.close();});
  const root=`http://127.0.0.1:${server.address().port}`;
  const feed=createFeed({expected,url:root+"/latest.json"}), references=createContextFeed({expected,url:root+"/comparisons.json"});
  await Promise.all([feed.refresh(),references.refresh()]);
  function shown(clock=now+1000) {
    const fs=feed.state(),cs=references.state(),reading=fs.artifact.facilities[0];
    const points=mergeLiveHistory(cs.artifact.facilities[0],[reading.last_success],policy);
    return renderSummary(expected[0],facilityView(reading,fs.artifact,clock,fs.refreshFailed),cs.artifact,points,clock,cs.failed).replace(/<[^>]*>/g,"");
  }
  assert.match(shown(),/\+20 min/); assert.match(shown(),/Above usual/);
  live=latest(70); await feed.refresh();
  assert.match(shown(),/70 min/); assert.match(shown(),/\+50 min/);
  failLive=true; await feed.refresh();
  assert.match(shown(),/Comparison paused/); assert.doesNotMatch(shown(),/Above usual/);
  failLive=false; await feed.refresh(); failContext=true; await references.refresh();
  assert.match(shown(),/context unavailable/); assert.doesNotMatch(shown(),/\+50 min/);
  failContext=false; await references.refresh();
  assert.match(shown(now+1800000),/Comparison paused/);
});

test("reference expiration, malformed artifacts and minimum support fail closed",()=>{
  assert.equal(contextAvailable(fixture(),now+7200000),false);
  assert.equal(contextAvailable(fixture(),Date.parse("2026-09-15T05:00:00Z")),false);
  assert.equal(contextAvailable(fixture(),now-1),false);
  for(const mutate of [d=>{d.facilities=[];},d=>{d.facilities[0].models['2026-09-14'][0].support.days=7;},
    d=>{d.facilities[0].models['2026-09-14'][0].reference_end_exclusive='2026-09-15';},
    d=>{d.facilities[0].history[0][0]='bad';},d=>{d.facilities[0].models['2026-09-14'][0].distribution=[[20,2]];}]) {
    const data=fixture(); mutate(data); assert.throws(()=>validateContext(data,expected));
  }
});

test("selectable histories retain gaps, absolute values, deviations and accessible tables",()=>{
  const entry=fixture().facilities[0];
  const points=mergeLiveHistory(entry,[latest().facilities[0].last_success],policy);
  const chart=renderHistory(points,24,now,policy,at);
  assert.equal(chart.count,4);
  assert.match(chart.svg,/role="img"/); assert.match(chart.svg,/typical-band/); assert.match(chart.svg,/delta-line/);
  assert.equal((chart.svg.match(/class="wait-line"/g)??[]).length,2,"45-minute gap starts a separate segment");
  assert.match(chart.table,/scope="col"/); assert.match(chart.table,/Reference days/); assert.match(chart.table,/\+20/);
  const longer=[...[...points].map(p=>[new Date(Date.parse(p[0])-2*86400000).toISOString(),...p.slice(1)]),...points];
  assert.equal(renderHistory(longer,24,now,policy,at).count,4);
  assert.equal(renderHistory(longer,168,now,policy,at).count,8);
  assert.match(renderHistory([],24,now,policy,at).svg,/No observations/);
});

test("insufficient-history and missing-reading states never display fabricated baselines",()=>{
  const data=fixture();
  data.facilities[0].models['2026-09-14'][10]={...data.facilities[0].models['2026-09-14'][10],state:"insufficient_history",median:null,low:null,high:null,distribution:[]};
  const fresh=facilityView(latest().facilities[0],latest(),now);
  const html=renderSummary(expected[0],fresh,data,[],now,false);
  assert.match(html,/Insufficient history/); assert.doesNotMatch(html,/Above usual/);
  const missing=renderSummary(expected[0],facilityView(null,null,now),data,[],now,false);
  assert.match(missing,/No successful observation/);
});
