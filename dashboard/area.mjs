// M4 area view: how many hospitals in an area read above or below their own usual.
// Counts facilities from M1 comparisons; not occupancy, capacity or patient-weighted load.
import {escape, compareReading, contextAvailable} from "./comparisons.mjs";
import {facilityView} from "./latest.mjs";
import {ticks} from "./heatmap.mjs";

export function validateAreas(areas, expected) {
  const slugs=new Set(expected.map(f=>f.slug)), keys=new Set();
  if(!Array.isArray(areas) || areas[0]?.key!=="all") throw Error("Invalid areas");
  for(const area of areas) {
    if(typeof area.key!=="string" || keys.has(area.key) || typeof area.label!=="string" || typeof area.basis!=="string" ||
       !Array.isArray(area.slugs) || !area.slugs.length || new Set(area.slugs).size!==area.slugs.length ||
       area.slugs.some(s=>!slugs.has(s))) throw Error("Invalid area");
    keys.add(area.key);
  }
  if(areas[0].slugs.length!==expected.length) throw Error("All-hospitals area incomplete");
  return areas;
}

// Same rule as the focus summary: outer 10% of the reference plus the meaningful distance.
export function pointState(point, policy) {
  if(point[2]===null) return "no_range";
  if(point[6]>=policy.unusual_high && point[5]>=policy.meaningful_minutes) return "above";
  if(point[6]<=policy.unusual_low && point[5]<=-policy.meaningful_minutes) return "below";
  return "near";
}
const comparisonState={above_usual:"above",below_usual:"below",no_large_departure:"near",insufficient_history:"no_range"};

export function currentArea(area, {context, live, now, contextFailed=false}) {
  const paused=!contextAvailable(context,now,contextFailed);
  const facilities=area.slugs.map(slug=>{
    const view=facilityView(live?.artifact?.facilities.find(f=>f.slug===slug),live?.artifact,now,live?.refreshFailed);
    if(!view.current || view.value===null) return {slug,state:"not_current"};
    if(paused) return {slug,state:"paused"};
    const entry=context.facilities.find(f=>f.slug===slug);
    const comparison=compareReading(entry,view.observedAt,view.value,context.policy);
    return {slug,state:comparisonState[comparison.state],delta:comparison.delta ?? null};
  });
  const count=state=>facilities.filter(f=>f.state===state).length;
  return {paused,facilities,total:area.slugs.length,above:count("above"),below:count("below"),
    compared:facilities.filter(f=>["above","below","near"].includes(f.state)).length,
    noRange:count("no_range"),notCurrent:count("not_current")};
}

export function binArea(context, area, hours) {
  const binMs=(hours<=24 ? 15 : 60)*60000;
  const end=Math.ceil(Date.parse(context.generated_at)/binMs)*binMs, start=end-hours*3600000;
  const columns=Math.round((end-start)/binMs);
  const bins=Array.from({length:columns},(_,i)=>({start:start+i*binMs,reporting:0,compared:0,above:[],below:[]}));
  const perFacility=new Map(area.slugs.map(slug=>[slug,{above:0,below:0,compared:0,reporting:0}]));
  for(const slug of area.slugs) {
    // The latest reading in each period stands for that facility, like a snapshot at the period's end.
    const latest=new Map();
    for(const point of context.facilities.find(f=>f.slug===slug)?.history ?? []) {
      const at=Date.parse(point[0]);
      if(at>=start && at<end) latest.set(Math.floor((at-start)/binMs),point);
    }
    const tally=perFacility.get(slug);
    for(const [index,point] of latest) {
      const bin=bins[index], state=pointState(point,context.policy);
      bin.reporting++; tally.reporting++;
      if(state==="no_range") continue;
      bin.compared++; tally.compared++;
      if(state==="above") { bin.above.push(slug); tally.above++; }
      if(state==="below") { bin.below.push(slug); tally.below++; }
    }
  }
  const counts=bins.filter(b=>b.compared).map(b=>b.above.length).sort((a,b)=>a-b);
  const typical=counts.length ? counts[Math.floor((counts.length-1)/2)] : null;
  return {start,end,binMs,columns,hours,total:area.slugs.length,bins,perFacility,typicalAbove:typical,
    periodsWithAbove:bins.filter(b=>b.above.length).length,compared:bins.filter(b=>b.compared).length};
}

const dayFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",month:"short",day:"numeric"});
const timeFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"2-digit"});

export function renderAreaChart(model, names, {width=900, full=names}={}) {
  const left=46, right=width-12, top=12, rowUnit=Math.max(10,Math.min(24,Math.floor(150/Math.max(1,model.total))));
  const axis=top+model.total*rowUnit, bottom=axis+model.total*rowUnit;
  const columnWidth=(right-left)/model.columns, gap=columnWidth>6 ? 1 : 0;
  const y=count=>axis-count*rowUnit;
  const list=slugs=>slugs.map(s=>names.get(s) ?? s).join(", ");
  let content=`<title id="area-title">Hospitals above or below their own usual, ${model.hours} hours</title>`+
    `<desc id="area-description">Columns are ${model.binMs/60000}-minute periods in America/Chicago time. Bars above the line count hospitals above usual; bars below count hospitals below usual. `+
    "Pale columns show how many hospitals had a reading with a usual range. A summary table follows.</desc>";
  const step=model.total>6 ? Math.ceil(model.total/3) : 1;
  for(let count=0;count<=model.total;count+=step) {
    for(const sign of count ? [1,-1] : [1]) {
      const yy=y(sign*count);
      content+=`<line class="${count ? "area-grid" : "area-zero"}" x1="${left}" x2="${right}" y1="${yy}" y2="${yy}"/>`+
        `<text x="${left-8}" y="${yy+6}" text-anchor="end">${count}</text>`;
    }
  }
  model.bins.forEach((bin,i)=>{
    if(!bin.reporting) return;
    const x=(left+i*columnWidth).toFixed(2), w=Math.max(1,columnWidth-gap).toFixed(2);
    const when=`${dayFormat.format(bin.start)}, ${timeFormat.format(bin.start)}–${timeFormat.format(bin.start+model.binMs)}`;
    const detail=`${bin.above.length} above usual${bin.above.length ? ` (${list(bin.above)})` : ""}; ${bin.below.length} below${bin.below.length ? ` (${list(bin.below)})` : ""}; ${bin.compared} of ${model.total} with a usual range`;
    content+=`<g class="area-column"><title>${escape(when)}: ${escape(detail)}</title>`+
      `<rect class="area-compared" x="${x}" y="${y(bin.compared)}" width="${w}" height="${bin.compared*rowUnit}"/>`+
      (bin.above.length ? `<rect class="area-above" x="${x}" y="${y(bin.above.length)}" width="${w}" height="${bin.above.length*rowUnit}"/>` : "")+
      (bin.below.length ? `<rect class="area-below" x="${x}" y="${axis}" width="${w}" height="${bin.below.length*rowUnit}"/>` : "")+
      `<rect class="area-hit" x="${x}" y="${top}" width="${w}" height="${bottom-top}"/></g>`;
  });
  for(const tick of ticks(model,Math.max(2,Math.floor((right-left)/110)))) {
    const x=left+tick.index*columnWidth;
    content+=`<line class="area-tick" x1="${x}" x2="${x}" y1="${bottom}" y2="${bottom+6}"/>`+
      `<text x="${x}" y="${bottom+26}" text-anchor="middle">${escape(dayFormat.format(tick.at))}<tspan x="${x}" dy="20">${escape(timeFormat.format(tick.at))}</tspan></text>`;
  }
  const svg=`<svg viewBox="0 0 ${width} ${bottom+56}" role="group" aria-labelledby="area-title area-description">${content}</svg>`;
  const table='<table><caption>Periods in this window by hospital (latest reading in each period)</caption><thead><tr>'+
    '<th scope="col">Hospital</th><th scope="col">Periods with readings</th><th scope="col">With usual range</th>'+
    '<th scope="col">Above usual</th><th scope="col">Below usual</th></tr></thead><tbody>'+
    [...model.perFacility].map(([slug,t])=>`<tr><th scope="row">${escape(full.get(slug) ?? slug)}</th><td>${t.reporting}</td><td>${t.compared}</td><td>${t.above}</td><td>${t.below}</td></tr>`).join("")+
    "</tbody></table>";
  return {svg,table};
}

export function renderAreaNow(current, names) {
  if(current.paused) return '<p class="area-count">Comparisons paused<small> · historical context unavailable or out of date</small></p>';
  const listed=state=>current.facilities.filter(f=>f.state===state).map(f=>names.get(f.slug) ?? f.slug);
  const above=listed("above"), below=listed("below");
  const detail=[`${current.compared} of ${current.total} compared now`,
    current.noRange ? `${current.noRange} without a usual range` : "",
    current.notCurrent ? `${current.notCurrent} not recently collected` : ""].filter(Boolean).join(" · ");
  return `<p class="area-count"><strong>${current.above}</strong> above usual <span class="area-of">of ${current.compared}</span>`+
    `<span class="area-below-count"><strong>${current.below}</strong> below</span></p>`+
    `<p class="area-detail">${escape(detail)}</p>`+
    (above.length ? `<p class="area-names"><span class="area-marker above" aria-hidden="true">▲</span> ${escape(above.join(", "))}</p>` : "")+
    (below.length ? `<p class="area-names"><span class="area-marker below" aria-hidden="true">▼</span> ${escape(below.join(", "))}</p>` : "");
}

export function mountArea(root, {expected, areas}) {
  const select=root.querySelector("select"), summary=root.querySelector(".area-now"), chart=root.querySelector(".area-chart");
  const table=root.querySelector(".area-table"), note=root.querySelector(".area-note");
  const names=new Map(expected.map(f=>[f.slug,f.display_name]));
  const short=new Map(expected.map(f=>[f.slug,f.short_name ?? f.display_name]));
  select.innerHTML=areas.map(a=>`<option value="${escape(a.key)}">${escape(a.label)} · ${a.slugs.length}</option>`).join("");
  let lastKey="";
  return {
    render({context, live, hours, contextFailed, now=Date.now()}) {
      const area=areas.find(a=>a.key===select.value) ?? areas[0];
      select.title=area.basis;
      summary.innerHTML=renderAreaNow(currentArea(area,{context,live,now,contextFailed}),short);
      const width=Math.max(560,Math.floor(chart.getBoundingClientRect().width || 900));
      const key=JSON.stringify([area.key,context?.generated_at,hours,width]);
      if(key===lastKey) return;
      lastKey=key;
      if(!context) { chart.innerHTML="<p>History is unavailable until a valid comparison artifact loads.</p>"; table.innerHTML=""; note.textContent=""; return; }
      const model=binArea(context,area,hours), view=renderAreaChart(model,short,{width,full:names});
      chart.innerHTML=view.svg; table.innerHTML=view.table;
      note.textContent=`${area.basis} · typical ${model.hours<=24 ? "24-hour" : "7-day"} count above usual: ${model.typicalAbove ?? "unavailable"} · `+
        `through ${dayFormat.format(model.end)}, ${timeFormat.format(model.end)}`;
    },
    onChange(listener) { select.addEventListener("change",listener); }
  };
}
