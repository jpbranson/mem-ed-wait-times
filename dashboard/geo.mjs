// M3 geographic placement: each hospital at its campus center, colored with the heatmap's
// period values, plus a replay through the shared time window. Descriptive only: being
// near each other on the map is not evidence that patients moved between hospitals.
import {bandOf, binHeatmap, span} from "./heatmap.mjs";
import {escape, signed} from "./comparisons.mjs";

// Direction is carried by a glyph as well as color.
export const glyphs = {above:"▲", below:"▼", near:"●", unsupported:"?", empty:"–"};
const STEP_MS = 700;

export function markerState(cell) {
  if(!cell?.readings) return {kind:"empty",band:"empty",glyph:glyphs.empty,text:"no reading"};
  if(cell.delta===null) return {kind:"unsupported",band:"unsupported",glyph:glyphs.unsupported,text:"no usual range"};
  const kind=cell.delta>10 ? "above" : cell.delta<-10 ? "below" : "near";
  return {kind,band:bandOf(cell.delta),glyph:glyphs[kind],text:`median ${signed(cell.delta)} min from usual`};
}

// One entry per hospital with a campus point, for the replayed period.
export function snapshot(model, index, expected) {
  const places=new Map(expected.filter(f=>f.campus).map(f=>[f.slug,f.campus]));
  const period={start:model.start+index*model.binMs};
  return model.rows.filter(row=>places.has(row.slug)).map(row=>{
    const state=markerState(row.cells[index]);
    return {slug:row.slug,name:row.name,full:row.full,...places.get(row.slug),...state,
      label:`${row.full}: ${state.text}, ${span(period,model.binMs)}`};
  });
}

// Keep the replayed period across rebuilds while it stays in the window; otherwise the latest.
export function resolveIndex(model, {start=null, follow=true}={}) {
  if(follow || start===null) return model.columns-1;
  const index=Math.round((start-model.start)/model.binMs);
  return index>=0 && index<model.columns ? index : model.columns-1;
}

const loadMap=options=>import("./geo-map.mjs").then(module=>module.createGeoMap(options));

export function mountGeo(root, {expected, areas=[], onSelect=()=>{}, onPeriod=()=>{}, createMap=loadMap,
  Observer=globalThis.IntersectionObserver, every=(fn,ms)=>setInterval(fn,ms), cancel=id=>clearInterval(id)}) {
  const slider=root.querySelector(".geo-slider"), play=root.querySelector(".geo-play"), latest=root.querySelector(".geo-latest");
  const period=root.querySelector(".geo-period"), container=root.querySelector(".geo-map"), status=root.querySelector(".geo-status");
  const view=root.querySelector(".geo-area");
  let model=null, index=null, start=null, follow=true, focus=null, map=null, pending=false, timer=null, lastKey="";
  // Views reuse the area groups (all hospitals, states, 50 km neighbor groups) to separate
  // clusters such as the Memphis area's seven campuses.
  view.innerHTML=areas.map(a=>`<option value="${escape(a.key)}">${escape(a.label)}</option>`).join("");
  const framed=()=>areas.find(a=>a.key===view.value)?.slugs ?? expected.map(f=>f.slug);
  view.addEventListener("change",()=>map?.fit(framed()));

  function show() {
    const ready=!!model;
    slider.disabled=play.disabled=!ready;
    latest.disabled=!ready || follow;
    if(!ready) { period.textContent="No history to replay"; onPeriod(null); return; }
    const text=span({start:model.start+index*model.binMs},model.binMs);
    slider.max=String(model.columns-1);
    slider.value=String(index);
    slider.setAttribute("aria-valuetext",text);
    period.textContent=follow ? `${text} · latest` : text;
    onPeriod(index);
    map?.update(snapshot(model,index,expected),focus);
  }
  function stop() {
    if(timer!==null) { cancel(timer); timer=null; }
    play.textContent="Play";
    play.setAttribute("aria-pressed","false");
  }
  function choose(next) {
    index=next; start=model.start+index*model.binMs; follow=index===model.columns-1; show();
  }
  slider.addEventListener("input",()=>{ if(!model) return; stop(); choose(Number(slider.value)); });
  latest.addEventListener("click",()=>{ if(!model) return; stop(); choose(model.columns-1); });
  play.addEventListener("click",()=>{
    if(timer!==null || !model) return stop();
    if(index>=model.columns-1) choose(0);
    play.textContent="Pause";
    play.setAttribute("aria-pressed","true");
    timer=every(()=>{ if(!model || index>=model.columns-1) return stop(); choose(index+1); },STEP_MS);
  });

  async function startMap() {
    if(map || pending) return;
    pending=true; status.textContent="Loading map…";
    try {
      map=await createMap({container,points:expected.filter(f=>f.campus),onSelect,
        onStatus:message=>{ status.textContent=message; }});
      status.textContent="";
      if(view.value && view.value!==areas[0]?.key) map.fit(framed());
      if(model) map.update(snapshot(model,index,expected),focus);
    } catch { status.textContent="Map unavailable · the heatmap above shows the same values"; }
    finally { pending=false; }
  }
  // Map code and tiles load only when the section nears the viewport.
  if(Observer) {
    const observer=new Observer(entries=>{ if(entries.some(e=>e.isIntersecting)) { observer.disconnect(); startMap(); } },{rootMargin:"200px"});
    observer.observe(container);
  } else startMap();
  show();

  return {
    render(context, hours, selected) {
      const key=JSON.stringify([context?.generated_at,hours,selected]);
      if(key===lastKey) return;
      lastKey=key; focus=selected;
      if(!context) { stop(); model=null; show(); return; }
      const previous=model;
      model=binHeatmap(context,expected,hours);
      if(!previous || previous.binMs!==model.binMs) follow=true;  // A new window starts at its latest period.
      index=resolveIndex(model,{start,follow});
      follow=index===model.columns-1;
      start=model.start+index*model.binMs;
      show();
    },
    stop
  };
}
