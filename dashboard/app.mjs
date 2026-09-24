import {createFeed, facilityView} from "./latest.mjs";
import {validateContext, contextAvailable, mergeLiveHistory, renderSummary, renderHistory} from "./comparisons.mjs";
import {mountTravel} from "./travel.mjs";
import {mountHeatmap} from "./heatmap.mjs";
import {mountArea, validateAreas} from "./area.mjs";

export function createContextFeed({expected, url="comparisons.json", fetcher=globalThis.fetch, onChange=()=>{}}) {
  let artifact=null, failed=false, pending=false;
  return {
    state:()=>({artifact,failed}),
    async refresh() {
      if(pending) return;
      pending=true;
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),10000);
      try {
        // Revalidate an unchanged hourly artifact instead of downloading it again.
        const response=await fetcher(url,{cache:"no-cache",signal:controller.signal});
        if(!response.ok) throw Error("Comparison fetch failed");
        const candidate=validateContext(await response.json(),expected);
        if(artifact && Date.parse(candidate.generated_at)<Date.parse(artifact.generated_at)) throw Error("Comparison artifact regressed");
        artifact=candidate; failed=false;
      } catch { failed=true; }
      finally { clearTimeout(timer); pending=false; onChange({artifact,failed}); }
    }
  };
}

if(typeof document!=="undefined" && document.getElementById("hospital-select")) {
  const expected=JSON.parse(document.getElementById("facility-registry").textContent);
  const selector=document.getElementById("hospital-select");
  const hours=document.getElementById("history-hours");
  const summary=document.getElementById("hospital-summary");
  const graph=document.getElementById("history-chart");
  const table=document.getElementById("history-table");
  const liveStatus=document.getElementById("refresh-status");
  const contextStatus=document.getElementById("context-status");
  const readings=new Map();
  let live={artifact:null,refreshFailed:false}, context={artifact:null,failed:false};
  let lastChartKey="";
  const travel=mountTravel(document.getElementById("travel-stage"),{expected,getLive:()=>live});
  const area=mountArea(document.getElementById("area-stage"),{expected,
    areas:validateAreas(JSON.parse(document.getElementById("area-groups").textContent),expected)});
  area.onChange(()=>render());
  const heatmap=mountHeatmap(document.getElementById("heatmap-stage"),{expected,onSelect:slug=>{
    selector.value=slug; render();
    document.querySelector(".focus-stage").scrollIntoView({block:"start",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
  }});
  function render() {
    const now=Date.now();
    travel.render();
    heatmap.render(context.artifact,Number(hours.value),selector.value);
    area.render({context:context.artifact,live,hours:Number(hours.value),contextFailed:context.failed,now});
    const facility=expected.find(f=>f.slug===selector.value);
    const item=live.artifact?.facilities.find(f=>f.slug===facility.slug);
    const freshness=facilityView(item,live.artifact,now,live.refreshFailed);
    const entry=context.artifact?.facilities.find(f=>f.slug===facility.slug);
    const policy=context.artifact?.policy;
    const seen=readings.get(facility.slug) ?? [];
    const points=policy ? mergeLiveHistory(entry,seen,policy) : [];
    const supportOpen=summary.querySelector(".support-details")?.open;
    const supportFocused=summary.querySelector(".support-details summary")===document.activeElement;
    const graphicWidth=Math.max(260,Math.min(340,Math.floor(summary.getBoundingClientRect().width)));
    summary.innerHTML=renderSummary(facility,freshness,context.artifact,points,now,context.failed,graphicWidth);
    if(supportOpen) summary.querySelector(".support-details")?.setAttribute("open","");
    if(supportFocused) summary.querySelector(".support-details summary")?.focus({preventScroll:true});
    liveStatus.textContent=live.refreshFailed ? "Live refresh failed" : live.artifact ? "Live feed loaded" : "Loading readings…";
    contextStatus.textContent=context.failed ? "Context refresh failed · retained history" :
      contextAvailable(context.artifact,now) ? "" : "Context out of date · comparisons paused";
    // Don't rebuild the accessible table every age tick; preserve keyboard focus.
    const chartWidth=Math.max(320,Math.floor(graph.getBoundingClientRect().width));
    const key=JSON.stringify([facility.slug,hours.value,context.artifact?.generated_at,seen.at(-1)?.observed_at,Math.floor(now/300000),chartWidth]);
    if(key!==lastChartKey) {
      const chart=policy ? renderHistory(points,Number(hours.value),now,policy,context.artifact.generated_at,chartWidth) :
        {svg:"<p>History is unavailable until a valid comparison artifact loads.</p>",table:""};
      graph.innerHTML=chart.svg; table.innerHTML=chart.table; lastChartKey=key;
    }
  }
  const feed=createFeed({expected,onChange:state=>{
    live=state;
    for(const item of state.artifact?.facilities ?? []) {
      if(!item.last_success) continue;
      const series=readings.get(item.slug) ?? [];
      if(!series.some(r=>r.observed_at===item.last_success.observed_at)) series.push(item.last_success);
      const cutoff=Date.now()-7*86400000;
      readings.set(item.slug,series.filter(r=>Date.parse(r.observed_at)>=cutoff).sort((a,b)=>Date.parse(a.observed_at)-Date.parse(b.observed_at)));
    }
    document.getElementById("latest-waits").innerHTML=state.html;
    render();
  }});
  const reference=createContextFeed({expected,onChange:state=>{context=state; render();}});
  selector.addEventListener("change",render);
  hours.addEventListener("change",render);
  document.addEventListener("history-window-change",event=>{hours.value=String(event.detail); render();});
  document.getElementById("refresh-waits").addEventListener("click",()=>Promise.all([feed.refresh(),reference.refresh(),travel.refresh()]));
  const widths=new Map();
  const resize=new ResizeObserver(entries=>{
    let changed=false;
    for(const entry of entries) {
      const width=Math.floor(entry.contentRect.width);
      if(width!==widths.get(entry.target)) { widths.set(entry.target,width); changed=true; }
    }
    if(changed) render();
  });
  resize.observe(graph); resize.observe(summary); resize.observe(document.querySelector(".heatmap-chart")); resize.observe(document.querySelector(".area-chart"));
  render();
  async function pollLatest() { await feed.refresh(); setTimeout(pollLatest,(live.artifact?.freshness.refresh_seconds ?? 60)*1000); }
  async function pollContext() { await Promise.all([reference.refresh(),travel.refresh()]); setTimeout(pollContext,300000); }
  pollLatest(); pollContext();
  setInterval(render,15000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden) {render(); feed.refresh(); reference.refresh();travel.refresh();}});
}
