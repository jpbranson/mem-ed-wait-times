// M3 first view: every hospital's difference from its own usual median, binned over time.
// Exploratory and descriptive; it does not show patient movement or a forecast.
import {escape, signed} from "./comparisons.mjs";

// Diverging steps: cool below, warm above, neutral within the M1 meaningful distance.
export const bands = [
  {key:"below-3", test:d=>d<=-40, label:"40+ below"},
  {key:"below-2", test:d=>d<=-20, label:"20–40 below"},
  {key:"below-1", test:d=>d<-10, label:"10–20 below"},
  {key:"near", test:d=>d<=10, label:"Within 10"},
  {key:"above-1", test:d=>d<20, label:"10–20 above"},
  {key:"above-2", test:d=>d<40, label:"20–40 above"},
  {key:"above-3", test:()=>true, label:"40+ above"},
];
export const bandOf = delta => bands.find(b=>b.test(delta)).key;
const median = values => {
  const sorted=[...values].sort((a,b)=>a-b), mid=Math.floor(sorted.length/2);
  return sorted.length%2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
};

export function binHeatmap(context, expected, hours) {
  const binMs=(hours<=24 ? 15 : 60)*60000;
  // Bins end at the prepared history's cutoff, aligned to clock boundaries.
  const end=Math.ceil(Date.parse(context.generated_at)/binMs)*binMs, start=end-hours*3600000;
  const columns=Math.round((end-start)/binMs);
  const entries=new Map(context.facilities.map(f=>[f.slug,f]));
  const rows=expected.map(facility=>{
    const cells=Array.from({length:columns},(_,i)=>({start:start+i*binMs,readings:0,deltas:[]}));
    for(const p of entries.get(facility.slug)?.history ?? []) {
      const at=Date.parse(p[0]);
      if(at<start || at>=end) continue;
      const cell=cells[Math.floor((at-start)/binMs)];
      cell.readings++;
      if(p[5]!==null) cell.deltas.push(p[5]);
    }
    return {slug:facility.slug,name:facility.short_name ?? facility.display_name,full:facility.display_name,
      cells:cells.map(c=>({start:c.start,readings:c.readings,supported:c.deltas.length,
        delta:c.deltas.length ? median(c.deltas) : null}))};
  });
  return {start,end,binMs,columns,hours,rows};
}

export function summarize(row) {
  const supported=row.cells.filter(c=>c.delta!==null);
  const above=supported.filter(c=>c.delta>10), below=supported.filter(c=>c.delta<-10);
  return {observed:row.cells.filter(c=>c.readings).length,supported:supported.length,above:above.length,below:below.length,
    largest:above.length ? Math.max(...above.map(c=>c.delta)) : null};
}

const dayFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",month:"short",day:"numeric"});
const timeFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"2-digit"});
const span=(cell,binMs)=>`${dayFormat.format(cell.start)}, ${timeFormat.format(cell.start)}–${timeFormat.format(cell.start+binMs)}`;

const hourFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"numeric",hourCycle:"h23"});
// Label Chicago midnights (7 days) or 6-hour marks (24 hours), thinned to fit and kept off the edges.
export function ticks(model, limit) {
  const every=model.hours<=24 ? 6 : 24, marks=[];
  for(let index=1;index<model.columns;index++) {
    const at=model.start+index*model.binMs;
    const [hour,minute]=hourFormat.format(at).split(":").map(Number);
    if(minute===0 && hour%every===0) marks.push({index,at});
  }
  const step=Math.ceil(marks.length/Math.max(1,limit));
  return marks.filter((_,i)=>i%step===0);
}

export function renderHeatmap(model, {width=900, focus=null}={}) {
  const labelWidth=width<640 ? 168 : 190, right=width-12, top=8, rowHeight=24, gap=2;
  const cellWidth=(right-labelWidth)/model.columns, bottom=top+model.rows.length*rowHeight;
  let content=`<title id="heatmap-title">Difference from usual by hospital over ${model.hours} hours</title>`+
    `<desc id="heatmap-description">Rows are hospitals; columns are ${model.binMs/60000}-minute periods in America/Chicago time. `+
    "Color shows the median minutes above or below that hospital's usual median. Blank periods have no reading; hatched periods lack a usual range. A summary table follows.</desc>"+
    '<defs><pattern id="heat-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="heat-hatch-line"/></pattern></defs>';
  model.rows.forEach((row,r)=>{
    const y=top+r*rowHeight, selected=row.slug===focus;
    content+=`<g class="heat-row${selected ? " selected" : ""}" data-slug="${escape(row.slug)}" role="button" tabindex="0" aria-pressed="${selected}" aria-label="${escape(row.full)}: show in focus chart">`+
      `<rect class="heat-row-hit" x="0" y="${y}" width="${right}" height="${rowHeight}"/>`+
      `<text class="heat-label" x="${labelWidth-10}" y="${y+rowHeight/2+6}" text-anchor="end">${escape(row.name)}</text>`;
    row.cells.forEach((cell,i)=>{
      if(!cell.readings) return;
      const x=labelWidth+i*cellWidth, w=Math.max(1,cellWidth-(cellWidth>8 ? gap : 0));
      const fill=cell.delta===null ? 'class="heat-cell heat-unsupported" fill="url(#heat-hatch)"' : `class="heat-cell heat-${bandOf(cell.delta)}"`;
      const detail=cell.delta===null ? "no usual range" : `median ${signed(cell.delta)} min from usual`;
      content+=`<rect ${fill} x="${x.toFixed(2)}" y="${y+gap/2}" width="${w.toFixed(2)}" height="${rowHeight-gap}">`+
        `<title>${escape(row.full)} · ${escape(span(cell,model.binMs))}: ${detail} (${cell.readings} reading${cell.readings===1?"":"s"})</title></rect>`;
    });
    content+="</g>";
  });
  for(const tick of ticks(model,Math.max(2,Math.floor((right-labelWidth)/110)))) {
    const x=labelWidth+tick.index*cellWidth;
    content+=`<line class="heat-tick" x1="${x}" x2="${x}" y1="${bottom}" y2="${bottom+6}"/>`+
      `<text x="${x}" y="${bottom+26}" text-anchor="middle">${escape(dayFormat.format(tick.at))}<tspan x="${x}" dy="20">${escape(timeFormat.format(tick.at))}</tspan></text>`;
  }
  const svg=`<svg viewBox="0 0 ${width} ${bottom+56}" role="group" aria-labelledby="heatmap-title heatmap-description">${content}</svg>`;
  const table='<table><caption>Periods by hospital in this window (median difference from usual median)</caption><thead><tr>'+
    '<th scope="col">Hospital</th><th scope="col">Periods with readings</th><th scope="col">With usual range</th>'+
    '<th scope="col">10+ min above</th><th scope="col">10+ min below</th><th scope="col">Largest above (min)</th></tr></thead><tbody>'+
    model.rows.map(row=>{
      const s=summarize(row);
      return `<tr><th scope="row">${escape(row.full)}</th><td>${s.observed}</td><td>${s.supported}</td><td>${s.above}</td><td>${s.below}</td><td>${s.largest===null ? "None" : signed(s.largest)}</td></tr>`;
    }).join("")+"</tbody></table>";
  return {svg,table};
}

export function renderLegend() {
  return bands.map(b=>`<span><i class="heat-swatch heat-${b.key}"></i>${b.label}</span>`).join("")+
    '<span><i class="heat-swatch heat-unsupported-swatch"></i>No usual range</span><span><i class="heat-swatch heat-empty-swatch"></i>No reading</span>';
}

export function mountHeatmap(root, {expected, onSelect=()=>{}}) {
  const chart=root.querySelector(".heatmap-chart"), table=root.querySelector(".heatmap-table"), note=root.querySelector(".heatmap-note");
  root.querySelector(".heatmap-legend").innerHTML=renderLegend();
  let lastKey="";
  const choose=target=>{ const row=target.closest?.(".heat-row"); if(row) onSelect(row.dataset.slug); };
  chart.addEventListener("click",event=>choose(event.target));
  chart.addEventListener("keydown",event=>{
    if(event.key==="Enter" || event.key===" ") { event.preventDefault(); choose(event.target); }
  });
  return {
    render(context, hours, focus) {
      const width=Math.max(560,Math.floor(chart.getBoundingClientRect().width || 900));
      const key=JSON.stringify([context?.generated_at,hours,focus,width]);
      if(key===lastKey) return;
      lastKey=key;
      if(!context) { chart.innerHTML="<p>History is unavailable until a valid comparison artifact loads.</p>"; table.innerHTML=""; note.textContent=""; return; }
      const active=document.activeElement?.closest?.(".heat-row")?.dataset.slug;
      const model=binHeatmap(context,expected,hours), view=renderHeatmap(model,{width,focus});
      chart.innerHTML=view.svg; table.innerHTML=view.table;
      if(active) chart.querySelector(`.heat-row[data-slug="${CSS.escape(active)}"]`)?.focus({preventScroll:true});
      note.textContent=`Through ${dayFormat.format(model.end)}, ${timeFormat.format(model.end)} · ${model.binMs/60000}-minute periods · America/Chicago`;
    }
  };
}
