import {facilityView} from "./latest.mjs";
import {mountOriginPicker} from "./origin.mjs";
export {locate} from "./origin.mjs";

const escape = v => String(v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const time = v => typeof v === "string" && /T.*(Z|[+-]\d{2}:\d{2})$/.test(v) ? Date.parse(v) : NaN;
const number = v => typeof v === "number" && Number.isFinite(v) && v >= 0;
const minutes = v => v.toLocaleString("en-US", {maximumFractionDigits:1});
export const ageGroups = ["adult", "child"];

export function validateTravel(data, expected) {
  if(data?.schema_version!==1 || data.method_version!=="travel-wait-v1" || data.metric!=="CV_ED_Wait" ||
     !Number.isFinite(time(data.generated_at)) || data.recommendations_enabled!==false ||
     !Array.isArray(data.facilities) || data.facilities.length!==expected.length) throw Error("Invalid travel context");
  // Do not accept an artifact that silently weakens this prototype's release gates.
  if(data.policy?.route_ttl_seconds!==300 || data.policy.context_ttl_seconds!==7200 ||
     data.policy.meaningful_minutes!==10) throw Error("Invalid travel policy");
  const seen=new Set();
  for(const f of data.facilities) {
    if(seen.has(f.slug) || !expected.some(e=>e.slug===f.slug) || typeof f.display_name!=="string" ||
       ageGroups.some(g=>f.eligibility?.[g]!==null && typeof f.eligibility?.[g]!=="string") ||
       !Array.isArray(f.movement) || f.movement.length!==4) throw Error("Invalid travel facility");
    seen.add(f.slug);
    f.movement.forEach((m,i)=>{
      if(m.horizon_minutes!==[15,30,60,120][i] || !Number.isSafeInteger(m.pairs) || m.pairs<0 ||
         !Number.isSafeInteger(m.days) || m.days<0 || m.days>28 ||
         (m.absolute_change_p90!==null && (!number(m.absolute_change_p90) || m.pairs<64 || m.days<8))) throw Error("Invalid movement support");
    });
  }
  return data;
}

export function availableContext(context, now) {
  const age=now-time(context?.generated_at);
  return !!context && age>=0 && age<7200000;
}

export function eligible(context, group) {
  return ageGroups.includes(group) ? (context?.facilities ?? []).filter(f=>f.eligibility[group]===null) : [];
}

export function validateRoutes(data, candidates, group) {
  if(data?.schema_version!==2 || data.provider!=="tomtom" || data.traffic_mode!=="live" ||
     !Number.isFinite(time(data.generated_at)) || data.ttl_seconds!==300 || data.age_group!==group ||
     !Array.isArray(data.routes) || data.routes.length!==candidates.length) throw Error("Invalid routes");
  const seen=new Set();
  for(const r of data.routes) {
    if(seen.has(r.slug) || !candidates.some(f=>f.slug===r.slug) || !["ok","unavailable"].includes(r.status) ||
       (r.status==="ok" ? !number(r.seconds) || !number(r.meters) ||
         (r.traffic_delay_seconds!==null && (!number(r.traffic_delay_seconds) || r.traffic_delay_seconds>r.seconds)) :
         r.seconds!==null || r.meters!==null || r.traffic_delay_seconds!==null)) throw Error("Invalid route");
    seen.add(r.slug);
  }
  return data;
}

export function compareTravel({context, routes, live, now=Date.now(), contextFailed=false}) {
  const paused=message=>({rows:[],closest:null,preferred:null,message});
  if(contextFailed || !availableContext(context,now)) return paused("Travel context unavailable · refresh to retry");
  if(!routes) return paused("Choose an origin to compare");
  const routeAge=(now-time(routes.generated_at))/1000;
  if(routeAge<0 || routeAge>=300) return paused("Road estimates expired · compare again");
  const candidates=eligible(context,routes.age_group);
  try { validateRoutes(routes,candidates,routes.age_group); } catch { return paused("Route coverage changed · compare again"); }
  if(!candidates.length) return paused("No verified destinations for this age group");
  const complete=routes.routes.every(r=>r.status==="ok");
  const sorted=[...routes.routes].sort((a,b)=>(a.seconds ?? Infinity)-(b.seconds ?? Infinity) || a.slug.localeCompare(b.slug));
  const closest=complete ? sorted[0].slug : null;
  const rows=sorted.map(r=>{
    const f=candidates.find(f=>f.slug===r.slug);
    const wait=facilityView(live?.artifact?.facilities.find(x=>x.slug===r.slug),live?.artifact,now,live?.refreshFailed);
    const drive=r.status==="ok" ? r.seconds/60 : null;
    const current=wait.current && number(wait.value);
    const horizon=f.movement.find(m=>m.horizon_minutes>=drive);
    return {slug:r.slug,name:f.display_name,drive,wait:current ? wait.value : null,
      total:drive!==null && current ? drive+wait.value : null,age:wait.age,
      reason:!current ? wait.value<0 ? "Wait interpretation unavailable" : wait.labels.join(" · ") : null,
      movement:drive!==null ? horizon ?? null : null,trafficDelay:r.traffic_delay_seconds};
  });
  const base=rows.find(r=>r.slug===closest);
  for(const r of rows) {
    r.extraDrive=base && r.drive!==null ? r.drive-base.drive : null;
    r.difference=base?.total!=null && r.total!==null ? base.total-r.total : null;
    const changes=[base?.movement?.absolute_change_p90,r.movement?.absolute_change_p90];
    r.screen=changes.every(number) ? 10+changes[0]+changes[1] : null;
    r.clearsMovementScreen=r.difference!==null && r.screen!==null && r.difference>r.screen;
  }
  // A descriptive movement screen cannot calibrate traffic or establish clinical benefit.
  return {rows,closest,preferred:null,routeAge,message:complete ? "Traffic-aware road estimates · live traffic where available · no recommendation" :
    "Some routes unavailable · closest and differences withheld"};
}

export function renderTravel(result, example=false) {
  if(!result.rows.length) return `<p class="travel-empty">${escape(result.message)}</p>`;
  const max=Math.max(1,...result.rows.map(r=>r.total ?? r.drive ?? 0));
  return `<p class="travel-caption">${example ? "Illustrative example · fictional hospitals and readings" : escape(result.message)}</p>`+
    '<div class="travel-key"><span><i class="drive-swatch"></i> Drive</span><span><i class="wait-swatch"></i> Published wait</span><span>Minutes</span></div>'+
    '<ol class="travel-rows">'+result.rows.map(r=>{
      const delta=r.difference===null ? "Difference unavailable" : r.slug===result.closest ? "Closest by road" :
        `${minutes(Math.abs(r.difference))} min ${r.difference>=0 ? "lower" : "higher"} estimate · +${minutes(r.extraDrive)} min driving`;
      const total=r.total===null ? "Unavailable" : `${minutes(r.total)} min`;
      const label=`${r.name}: ${r.drive===null ? "route unavailable" : minutes(r.drive)+" minutes driving"}; ${r.wait===null ? "wait unavailable" : r.wait+" minutes published wait"}; combined ${total}. ${delta}.`;
      return `<li><div class="travel-row-title"><span>${escape(r.name)}</span><strong>${total}</strong></div>`+
        `<div class="travel-bar" role="img" aria-label="${escape(label)}"><span class="drive-segment" style="width:${(r.drive ?? 0)/max*100}%"></span>`+
        `<span class="wait-segment" style="width:${(r.total!==null ? r.wait : 0)/max*100}%"></span></div>`+
        `<div class="travel-row-detail"><span>${r.drive===null ? "Route unavailable" : minutes(r.drive)+" drive"} + ${r.wait===null ? escape(r.reason ?? "Wait unavailable") : r.wait+" wait"}</span>`+
        `<span>${r.age===null ? "No observation" : `Collected ${Math.max(0,Math.floor(r.age/60))} min ago`}</span></div>`+
        `<p class="travel-difference">${escape(delta)}</p></li>`;
    }).join("")+"</ol>";
}

export function exampleComparison() {
  return {message:"",closest:"example-a",preferred:null,rows:[
    {slug:"example-a",name:"Example hospital A",drive:12,wait:80,total:92,age:180,extraDrive:0,difference:0},
    {slug:"example-b",name:"Example hospital B",drive:25,wait:35,total:60,age:300,extraDrive:13,difference:32},
    {slug:"example-c",name:"Example hospital C",drive:38,wait:50,total:88,age:120,extraDrive:26,difference:4}
  ]};
}

// Static hosting has no routing gateway; never send an origin until one confirms availability.
export async function probeRouting(fetcher=globalThis.fetch) {
  try {
    const response=await fetcher("/api/routes/status",{cache:"no-store",signal:AbortSignal.timeout(5000)});
    if(!response.ok) return false;
    const data=await response.json();
    return data?.schema_version===1 && data.available===true;
  } catch { return false; }
}

export function createRouteFeed({fetcher=globalThis.fetch, onChange=()=>{}}={}) {
  let serial=0,controller=null;
  return {
    clear() { serial++; controller?.abort(); controller=null; },
    async request(origin,context,group) {
      controller?.abort(); controller=new AbortController();
      const current=++serial, active=controller, signal=active.signal;
      const timer=setTimeout(()=>active.abort(),20000);
      let error="Road estimates unavailable · try again later";
      try {
        const response=await fetcher("/api/routes",{method:"POST",cache:"no-store",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({...origin,age_group:group}),signal});
        if(!response.ok) {
          const code=(await response.json()).error;
          const messages={request_budget_exhausted:"Routing allowance reached · estimates paused",
            provider_limit_reached:"Routing provider limit reached · try again later",
            routing_not_configured:"Routing is not available yet",
            routing_access_denied:"Routing is temporarily unavailable",
            no_verified_destinations:"Emergency destinations awaiting verification",
            rate_limited:"Another comparison is running · try again shortly"};
          if(Object.hasOwn(messages,code)) error=messages[code];
          throw Error("Route request failed");
        }
        const routes=validateRoutes(await response.json(),eligible(context,group),group);
        if(current===serial) onChange({routes,error:""});
      } catch { if(current===serial) onChange({routes:null,error}); }
      finally { clearTimeout(timer); }
    }
  };
}

export function mountTravel(root,{expected,getLive,fetcher=globalThis.fetch,originOptions={}}) {
  const form=root.querySelector("form"), group=root.querySelector("[name=age_group]");
  const status=root.querySelector(".travel-status"), chart=root.querySelector(".travel-chart");
  const submit=root.querySelector("[type=submit]");
  const exampleButton=root.querySelector(".travel-example"), support=root.querySelector(".travel-support");
  let context=null,failed=false,routes=null,error="",example=false,busy=false,pending=false,routing=null;
  const routeFeed=createRouteFeed({fetcher,onChange:state=>{routes=state.routes;error=state.error;busy=false;render();}});
  function invalidate() { routeFeed.clear();routes=null;error="";busy=false;example=false; }
  const origin=mountOriginPicker(root,{...originOptions,onChange:()=>{invalidate();render();}});
  function render() {
    const candidates=eligible(context,group.value);
    const available=!failed && availableContext(context,Date.now());
    submit.disabled=!available || !candidates.length || routing!==true || busy || origin.isLocating() || !origin.value();
    exampleButton.textContent=example ? "Close example" : "View example";
    exampleButton.setAttribute("aria-pressed",String(example));
    status.textContent=error || (busy ? "Calculating road estimates…" : !available ? "Travel context unavailable" :
      !group.value ? "Choose adult or child" : !candidates.length ? "Emergency destinations awaiting verification" :
      routing===null ? "Checking road estimate availability…" : routing===false ? `${candidates.length} verified destinations · road estimates not available on this site yet` :
      `${candidates.length} verified destinations`);
    const result=compareTravel({context,routes,live:getLive(),contextFailed:failed});
    chart.innerHTML=renderTravel(example ? exampleComparison() : !routes ? {...result,message:""} : result,example);
    const excluded=(context?.facilities ?? []).filter(f=>f.eligibility[group.value]);
    support.innerHTML=(excluded.length ? `<p>${excluded.length} excluded destinations</p><ul>`+excluded.map(f=>`<li>${escape(f.display_name)} · ${escape(f.eligibility[group.value])}</li>`).join("")+"</ul>" : "")+
      (result.rows.length ? `<p>TomTom road estimates requested ${Math.floor(result.routeAge/60)} min ago. Live traffic is requested; zero or missing delay does not establish coverage on every road.</p><ul>`+
        result.rows.map(r=>`<li>${escape(r.name)}: ${r.trafficDelay==null ? "traffic delay unavailable" : `${minutes(r.trafficDelay/60)} min reported traffic delay, already included in driving time`}</li>`).join("")+"</ul>"+
        "<p>90th percentile absolute change in published waits at the selected historical horizon; overlapping pairs, not independent patients or prediction intervals.</p><ul>"+
        result.rows.map(r=>`<li>${escape(r.name)}: ${r.movement?.absolute_change_p90==null ? "insufficient history or drive over 120 min" :
          `${minutes(r.movement.absolute_change_p90)} min at ${r.movement.horizon_minutes} min · ${r.movement.pairs} pairs / ${r.movement.days} days`}</li>`).join("")+"</ul>" : "");
  }
  async function refresh() {
    if(pending) return;
    pending=true;
    // Independent of the context fetch so a slow gateway never delays travel context.
    if(routing!==true) probeRouting(fetcher).then(ok=>{routing=ok;render();});
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await fetcher("travel.json",{cache:"no-cache",signal:controller.signal});
      if(!response.ok) throw Error("Travel context unavailable");
      const next=validateTravel(await response.json(),expected);
      if(context && time(next.generated_at)<time(context.generated_at)) throw Error("Travel context regressed");
      context=next;failed=false;
    } catch { failed=true; }
    finally { clearTimeout(timer);pending=false;render(); }
  }
  group.addEventListener("change",()=>{invalidate();render();});
  form.addEventListener("submit",event=>{
    event.preventDefault();
    if(!form.reportValidity() || submit.disabled) return;
    invalidate();busy=true;render();
    routeFeed.request(origin.value(),context,group.value);
  });
  exampleButton.addEventListener("click",()=>{example=!example;render();});
  render();
  return {render,refresh};
}
