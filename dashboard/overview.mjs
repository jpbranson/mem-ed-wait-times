// Fit the y-axis to the lines actually visible in the selected time window.
export function visibleYRange(traces, start, end) {
  let low=0, high=0, found=false;
  function include(value) { low=Math.min(low,value); high=Math.max(high,value); found=true; }
  for(const trace of traces) {
    if(trace.visible===false || trace.visible==="legendonly") continue;
    let previous=null;
    for(let i=0;i<(trace.x?.length ?? 0);i++) {
      const x=trace.x[i], y=trace.y[i];
      if(!Number.isFinite(x) || !Number.isFinite(y)) {previous=null; continue;}
      if(x>=start && x<=end) include(y);
      // Include the visible edge of a crossing segment, but never bridge a gap.
      if(previous && x>previous.x) for(const boundary of [start,end]) {
        if(previous.x<boundary && boundary<x) include(previous.y+(y-previous.y)*(boundary-previous.x)/(x-previous.x));
      }
      previous={x,y};
    }
  }
  if(!found || high===low) return [0,10];
  const span=high-low, step=10**Math.floor(Math.log10(span))/2;
  return [low<0 ? Math.floor((low-span*.06)/step)*step : 0,
          high>0 ? Math.ceil((high+span*.06)/step)*step : 0];
}

export function windowLayout(traces, hours, end, tickCount=5) {
  const start=end-hours*3600000;
  const ticks=Array.from({length:tickCount},(_,i)=>start+(end-start)*i/(tickCount-1));
  const day=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",month:"short",day:"numeric"});
  const time=new Intl.DateTimeFormat("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"2-digit"});
  return {"xaxis.range":[start,end],"xaxis.tickvals":ticks,
    "xaxis.ticktext":ticks.map(at=>`${day.format(at)}<br>${time.format(at)}`),
    "yaxis.autorange":false,"yaxis.range":visibleYRange(traces,start,end)};
}

export function attachOverview(plot, plotly, {tickCount=()=>5, onVisibility=()=>{}}={}) {
  let hours=168;
  const end=Date.parse(plot.layout.meta.generated_at);
  const fit=()=>plotly.relayout(plot,windowLayout(plot.data,hours,end,tickCount()));
  plot.on("plotly_restyle",()=>{fit(); onVisibility(plot.data);});
  return {
    setWindow(value) {hours=value; return fit();},
    toggle(index, isolate=false) {
      if(isolate) return plotly.restyle(plot,{visible:plot.data.map((_,i)=>i===index ? true : "legendonly")});
      return plotly.restyle(plot,{visible:plot.data[index].visible===false || plot.data[index].visible==="legendonly" ? true : "legendonly"},[index]);
    },
    showAll:()=>plotly.restyle(plot,{visible:true}),
    resize:()=>fit(),
  };
}

if(typeof document!=="undefined") {
  let controller=null, hours=168;
  const buttons=[...document.querySelectorAll("[data-overview-hours]")];
  const legend=[...document.querySelectorAll("[data-trace-index]")];
  function connect() {
    const plot=document.getElementById("all-hospitals-plot");
    if(controller || !plot?.data || !plot.on || !globalThis.Plotly) return;
    controller=attachOverview(plot,globalThis.Plotly,{
      tickCount:()=>Math.max(2,Math.min(5,Math.floor(plot.clientWidth/150))),
      onVisibility:traces=>{
        let count=0;
        traces.forEach((trace,i)=>{
          const shown=trace.visible!==false && trace.visible!=="legendonly";
          count+=shown; legend[i]?.setAttribute("aria-pressed",String(shown));
        });
        document.getElementById("overview-count").textContent=`${count} / ${traces.length} hospitals`;
      },
    });
    controller.setWindow(hours);
    // Re-measure labels once the locally served Inter font is ready.
    document.fonts?.ready.then(()=>controller.resize());
  }
  buttons.forEach(button=>button.addEventListener("click",()=>{
    hours=Number(button.dataset.overviewHours);
    buttons.forEach(other=>other.setAttribute("aria-pressed",String(other===button)));
    const field=document.getElementById("history-hours");
    if(field) field.value=String(hours);
    controller?.setWindow(hours);
    document.dispatchEvent(new CustomEvent("history-window-change",{detail:hours}));
  }));
  legend.forEach(button=>button.addEventListener("click",event=>controller?.toggle(Number(button.dataset.traceIndex),event.shiftKey || event.detail===2)));
  document.getElementById("overview-all")?.addEventListener("click",()=>controller?.showAll());
  document.addEventListener("overview-ready",connect);
  globalThis.addEventListener("resize",()=>controller?.resize());
  connect();
}
