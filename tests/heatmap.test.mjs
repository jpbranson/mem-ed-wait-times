import test from "node:test";
import assert from "node:assert/strict";
import {bandOf, binHeatmap, renderHeatmap, summarize, ticks} from "../dashboard/heatmap.mjs";

const expected=[{slug:"a",display_name:"Hospital <A>",short_name:"A"},{slug:"b",display_name:"Hospital B"}];
const generated="2026-09-14T16:05:00Z", end=Date.parse("2026-09-14T17:00:00Z"), hour=3600000;
const point=(at,value,delta)=>[new Date(at).toISOString(),value,delta===null?null:value-delta,null,null,delta,null,0,0,"weekday_weekend"];
const context=history=>({generated_at:generated,facilities:[{slug:"a",history},{slug:"b",history:[]}]});

test("bands are symmetric around the M1 ten-minute threshold",()=>{
  assert.deepEqual([-45,-40,-25,-20,-15,-10,0,10,15,20,39,40].map(bandOf),
    ["below-3","below-3","below-2","below-2","below-1","near","near","near","above-1","above-2","above-2","above-3"]);
});

test("7-day view uses clock-aligned hourly bins ending at the prepared cutoff",()=>{
  const model=binHeatmap(context([]),expected,168);
  assert.equal(model.binMs,hour); assert.equal(model.columns,168);
  assert.equal(model.end,end); assert.equal(model.start,end-168*hour);
  assert.equal(binHeatmap(context([]),expected,24).columns,96);
});

test("cells take the median supported difference, keep unsupported readings, and leave gaps empty",()=>{
  const at=end-2*hour;
  const model=binHeatmap(context([point(at,40,5),point(at+15*60000,60,30),point(at+30*60000,90,50),
    point(end-hour+60000,20,null),point(end-200*hour,10,-90)]),expected,168);
  const row=model.rows[0], cells=row.cells;
  assert.equal(cells[165].readings,0);
  assert.equal(cells[166].delta,30); assert.equal(cells[166].readings,3);
  assert.equal(cells[167].delta,null); assert.equal(cells[167].readings,1);
  assert.equal(cells.filter(c=>c.readings).length,2, "readings outside the window are ignored");
  assert.deepEqual(summarize(row),{observed:2,supported:1,above:1,below:0,largest:30});
  assert.equal(model.rows[1].cells.every(c=>c.readings===0),true, "a hospital without history keeps its row");
});

test("rendering escapes names, marks the focused row, and omits empty periods",()=>{
  const model=binHeatmap(context([point(end-2*hour,40,-25),point(end-hour,20,null)]),expected,168);
  const {svg,table}=renderHeatmap(model,{width:900,focus:"a"});
  assert.match(svg,/Hospital &lt;A&gt;/);
  assert.doesNotMatch(svg,/<A>/);
  assert.match(svg,/class="heat-row selected" data-slug="a"[^>]*aria-pressed="true"/);
  assert.equal((svg.match(/<rect class="heat-cell/g) ?? []).length,2);
  assert.match(svg,/heat-below-2/);
  assert.match(svg,/heat-unsupported/);
  assert.match(svg,/no usual range/);
  assert.match(table,/<th scope="row">Hospital B<\/th><td>0<\/td>/);
});

test("time labels fall on Chicago midnights or 6-hour marks, including across DST",()=>{
  const chicago=at=>new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"2-digit",hourCycle:"h23"}).format(at);
  const week=binHeatmap({generated_at:"2026-11-03T12:00:00Z",facilities:[]},expected,168);
  const marks=ticks(week,10);
  assert.equal(marks.length,7);
  assert.ok(marks.every(m=>chicago(m.at)==="00:00"), "midnight before and after the Nov 1 fall-back");
  const day=ticks(binHeatmap(context([]),expected,24),10);
  assert.deepEqual(day.map(m=>chicago(m.at)),["12:00","18:00","00:00","06:00"]);
  assert.equal(ticks(week,3).length,3, "thinned to fit narrow charts");
});
