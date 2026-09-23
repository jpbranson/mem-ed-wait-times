// Versioned facility context, computed from prior local days by edwait.analysis.
export const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const number = n => Number.isFinite(n);
const validTime = value => typeof value === "string" && /T.*(Z|[+-]\d{2}:\d{2})$/.test(value) && number(Date.parse(value));
const ordinal = n => { const whole=Math.round(n), tail=whole%100; return `${whole}${tail>=11&&tail<=13?"th":({1:"st",2:"nd",3:"rd"}[whole%10]??"th")}`; };
export const fmt = n => number(n) ? Number(n.toFixed(1)).toLocaleString("en-US") : "Unavailable";
export const signed = n => `${n > 0 ? "+" : ""}${fmt(n)}`;
export const when = value => new Date(value).toLocaleString("en-US", {timeZone:"America/Chicago", timeZoneName:"short"});
const parts = new Intl.DateTimeFormat("en-CA", {timeZone:"America/Chicago", year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", hourCycle:"h23"});
export function localGroup(at) {
  const fields = Object.fromEntries(parts.formatToParts(new Date(at)).map(p => [p.type, p.value]));
  return {day:`${fields.year}-${fields.month}-${fields.day}`, hour:Number(fields.hour)};
}

export function validateContext(data, expected) {
  if (data?.schema_version !== 1 || data.method_version !== "self-comparison-v1" || data.metric !== "CV_ED_Wait" ||
      data.local_timezone !== "America/Chicago" || !validTime(data.generated_at) ||
      !validTime(data.valid_until) || Date.parse(data.valid_until) <= Date.parse(data.generated_at) ||
      !Array.isArray(data.facilities) || data.facilities.length !== expected.length) throw Error("Invalid comparison artifact");
  for (const key of ["lookback_days", "hour_radius", "fallback_hour_radius", "minimum_days", "minimum_samples", "meaningful_minutes", "trend_minutes", "trend_tolerance_minutes", "trend_minimum_samples", "cadence_seconds", "gap_seconds"]) {
    if (!number(data.policy?.[key]) || data.policy[key] <= 0) throw Error("Invalid comparison policy");
  }
  for(const key of ["minimum_coverage","minimum_day_coverage","band_low","band_high"]) {
    if(!number(data.policy[key]) || data.policy[key]<0 || data.policy[key]>1) throw Error("Invalid reference fractions");
  }
  if(!number(data.policy.unusual_low) || !number(data.policy.unusual_high) || data.policy.unusual_low<0 ||
     data.policy.unusual_high>100 || data.policy.unusual_low>=data.policy.unusual_high) throw Error("Invalid unusualness thresholds");
  const seen = new Set();
  for (const f of data.facilities) {
    if (!expected.some(e => e.slug === f.slug) || seen.has(f.slug) || !Array.isArray(f.history) || !f.models) throw Error("Invalid comparison coverage");
    seen.add(f.slug);
    if(!f.models[localGroup(data.generated_at).day]) throw Error("Current local-day models missing");
    for (const [day,models] of Object.entries(f.models)) {
      if (!Array.isArray(models) || models.length !== 24) throw Error("Invalid hour models");
      for (const m of models) {
        if (!["supported", "insufficient_history"].includes(m.state) || !m.support || !Array.isArray(m.distribution)) throw Error("Invalid baseline");
        if(m.reference_end_exclusive!==day || !["weekday_weekend","wider_hours","all_days"].includes(m.group) ||
           !number(m.support.coverage) || m.support.coverage<0 || m.support.coverage>1 ||
           ["days","eligible_days","samples","expected_slots","observed_slots"].some(k=>!Number.isInteger(m.support[k])||m.support[k]<0)) throw Error("Invalid support or reference cutoff");
        if (m.state === "supported" && (![m.low,m.median,m.high].every(number) || m.low > m.median || m.median > m.high ||
            !m.distribution.length || m.distribution.some(([v,n],i) => !Number.isInteger(v) || !Number.isInteger(n) || n <= 0 || i>0 && v<=m.distribution[i-1][0]) ||
            m.distribution.reduce((sum,[,n])=>sum+n,0)!==m.support.samples || m.support.days<data.policy.minimum_days ||
            m.support.samples<data.policy.minimum_samples || m.support.coverage<data.policy.minimum_coverage)) throw Error("Invalid supported baseline");
        if(m.state==="insufficient_history" && (m.median!==null || m.low!==null || m.high!==null || m.distribution.length)) throw Error("Unsupported baseline has values");
      }
    }
    let previous = -Infinity;
    for (const point of f.history) {
      if (!Array.isArray(point) || point.length !== 10 || !validTime(point[0]) || Date.parse(point[0]) <= previous ||
          Date.parse(point[0]) > Date.parse(data.generated_at) || !Number.isInteger(point[1]) ||
          point.slice(2,7).some(v => v !== null && !number(v)) || !number(point[8]) || point[8]<0 || point[8]>1 ||
          point[2]!==null && (point[3]===null || point[4]===null || point[5]===null || point[6]===null || point[3]>point[2] || point[2]>point[4]) ||
          point[2]===null && point.slice(3,7).some(v=>v!==null)) throw Error("Invalid historical point");
      previous = Date.parse(point[0]);
    }
  }
  return data;
}

export function contextAvailable(context, now, failed=false) {
  if (!context || failed) return false;
  const age = now - Date.parse(context.generated_at);
  return age >= 0 && age < 2 * 3600000 && now < Date.parse(context.valid_until);
}

export function compareReading(entry, at, value, policy) {
  const {day,hour} = localGroup(at);
  const model = entry?.models?.[day]?.[hour];
  if (!model || model.state !== "supported") return {state:"insufficient_history", model};
  const distribution = model.distribution;
  const count = distribution.reduce((sum,[,n]) => sum + n,0);
  const percentile = 100 * distribution.reduce((sum,[v,n]) => sum + n * (v < value ? 1 : v === value ? .5 : 0),0) / count;
  const delta = value - model.median;
  const state = percentile >= policy.unusual_high && delta >= policy.meaningful_minutes ? "above_usual" :
    percentile <= policy.unusual_low && delta <= -policy.meaningful_minutes ? "below_usual" : "no_large_departure";
  return {state, model, delta, percentile};
}

export function recentDirection(points, at, value, policy) {
  const time = Date.parse(at);
  const low = time - (policy.trend_minutes + policy.trend_tolerance_minutes) * 60000;
  const high = time - (policy.trend_minutes - policy.trend_tolerance_minutes) * 60000;
  const sample = points.filter(p => Date.parse(p[0]) >= low && Date.parse(p[0]) <= high && Date.parse(p[0]) < time);
  if (sample.length < policy.trend_minimum_samples || sample.some((p,i) => i && Date.parse(p[0]) - Date.parse(sample[i-1][0]) > policy.gap_seconds * 1000)) {
    return {state:"insufficient_recent_history", delta:null, samples:sample.length};
  }
  const values = sample.map(p => p[1]).sort((a,b) => a-b);
  const middle = Math.floor(values.length / 2);
  const median = values.length % 2 ? values[middle] : (values[middle-1] + values[middle]) / 2;
  const delta = value - median;
  return {state:delta >= policy.meaningful_minutes ? "rising" : delta <= -policy.meaningful_minutes ? "falling" : "little_change", delta, samples:sample.length};
}

export function mergeLiveHistory(entry, readings, policy) {
  const points = new Map((entry?.history ?? []).map(p => [p[0],p]));
  for (const r of readings) {
    if (!points.has(r.observed_at)) {
      const comparison = compareReading(entry,r.observed_at,r.wait_minutes,policy);
      const m = comparison.model;
      points.set(r.observed_at,[r.observed_at,r.wait_minutes,m?.median ?? null,m?.low ?? null,m?.high ?? null,
        comparison.delta ?? null,comparison.percentile ?? null,m?.support.days ?? 0,m?.support.coverage ?? 0,m?.group ?? "unavailable"]);
    }
  }
  // Match preparation's one contribution per cadence slot, including retries
  // received while the page stays open and equivalent timestamp encodings.
  const slots = new Map();
  for (const point of [...points.values()].sort((a,b) => Date.parse(a[0])-Date.parse(b[0]) || a[1]-b[1])) {
    slots.set(Math.floor(Date.parse(point[0])/(policy.cadence_seconds*1000)),point);
  }
  return [...slots.values()];
}

const groups = {weekday_weekend:"Same weekday/weekend group; neighboring hours",wider_hours:"Fallback: wider hours, same weekday/weekend group",all_days:"Fallback: all days with wider hours"};
const states = {above_usual:"Above usual",below_usual:"Below usual",no_large_departure:"No large departure",insufficient_history:"Insufficient history"};
function referenceGraphic(model,value,width) {
  const low=Math.min(0,model.low,value), high=Math.max(1,model.high,value);
  const right=width-18, x=v=>18+(v-low)/(high-low)*(right-18);
  return `<svg class="reference-graphic" viewBox="0 0 ${width} 64" role="img" aria-label="Current reading ${value} minutes; typical range ${model.low} to ${model.high}; median ${model.median}">`+
    `<line class="reference-axis" x1="18" x2="${right}" y1="25" y2="25"/>`+
    `<rect class="typical-band" x="${x(model.low)}" y="16" width="${Math.max(2,x(model.high)-x(model.low))}" height="18" rx="3"/>`+
    `<line class="reference-median" x1="${x(model.median)}" x2="${x(model.median)}" y1="12" y2="38"/>`+
    `<circle class="reference-now" cx="${x(value)}" cy="25" r="5"/><text x="18" y="57">${fmt(low)}</text><text x="${right}" y="57" text-anchor="end">${fmt(high)} min</text></svg>`;
}
export function renderSummary(facility, freshness, context, points, now, contextFailed, graphicWidth=300) {
  const entry = context?.facilities.find(f => f.slug === facility.slug);
  const freshContext = contextAvailable(context,now,contextFailed);
  const comparison = freshContext && freshness.value !== null ? compareReading(entry,freshness.observedAt,freshness.value,context.policy) : null;
  const supported = freshness.current && comparison?.model?.state === "supported";
  const status = !freshness.current ? "Comparison paused · freshness unconfirmed" : !freshContext ? "Historical context unavailable" : states[comparison.state];
  const model = comparison?.model;
  const trend = supported ? recentDirection(points,freshness.observedAt,freshness.value,context.policy) : null;
  const direction = trend?.state === "rising" ? `↑ Up ${fmt(trend.delta)} min / 1h` :
    trend?.state === "falling" ? `↓ Down ${fmt(-trend.delta)} min / 1h` :
    trend?.state === "little_change" ? `→ Little change · ${signed(trend.delta)} min / 1h` : "Recent direction unavailable";
  const support = model ? `${model.support.days} contributing days of ${model.support.eligible_days} eligible; ${model.support.samples} reference readings; ${Math.round(model.support.coverage*100)}% slot coverage.` : "";
  const age=freshness.observedAt ? `<time datetime="${escape(freshness.observedAt)}" title="${escape(when(freshness.observedAt))}">${freshness.age<0?"Clock mismatch":`${Math.floor(freshness.age/60)}m ago`}</time>` : "No successful observation";
  return `<h2 class="visually-hidden">${escape(facility.display_name)}</h2>` +
    `<p class="wait-status">${escape(freshness.labels.join(" · "))} · ${age}</p>` +
    `<div class="headline-values"><div><span>${freshness.current ? "Published wait" : "Last reading"}</span><strong class="${freshness.value===null?'value-unavailable':''}">${freshness.value === null ? "Unavailable" : `${fmt(freshness.value)}<small> min</small>`}</strong></div>` +
    `<div class="deviation-value"><span>From usual</span><strong>${supported ? `${signed(comparison.delta)} min` : "Unavailable"}</strong></div></div>` +
    `<p class="comparison-state">${escape(status)}</p>` +
    (supported ? referenceGraphic(model,freshness.value,graphicWidth) : "") +
    `<dl class="comparison-metrics"><div><dt>Median</dt><dd>${supported ? `${fmt(model.median)} min` : "Unavailable"}</dd></div>` +
    `<div><dt>Typical 50%</dt><dd>${supported ? `${fmt(model.low)}–${fmt(model.high)} min` : "Unavailable"}</dd></div>` +
    `<div><dt>Percentile</dt><dd>${supported ? ordinal(comparison.percentile) : "Unavailable"}</dd></div></dl>` +
    `<p class="recent-direction">${escape(direction)}</p>` +
    (model ? `<details class="support-details"><summary>${model.support.days} days · ${Math.round(model.support.coverage*100)}% coverage</summary><p>${escape(support)} ${escape(groups[model.group])}</p></details>` : "");
}

function segments(points, valid, gap) {
  const output=[]; let current=[];
  for (const p of points) {
    if (!valid(p) || current.length && Date.parse(p[0])-Date.parse(current.at(-1)[0]) > gap) {
      if (current.length) output.push(current);
      current=[];
    }
    if (valid(p)) current.push(p);
  }
  if (current.length) output.push(current);
  return output;
}

export function renderHistory(points, hours, now, policy, generatedAt, availableWidth=800) {
  const start = now - hours*3600000;
  const visible = points.filter(p => Date.parse(p[0]) >= start && Date.parse(p[0]) <= now);
  if (!visible.length) return {svg:'<p>No observations in this history window.</p>',table:"",count:0};
  // Draw in display pixels rather than shrinking fixed-size SVG text on mobile.
  const width=Math.max(320,Math.floor(availableWidth)),left=58,right=width-18,top=32,bottom=236,deltaTop=336,deltaBottom=456;
  const low = Math.min(0,...visible.map(p => Math.min(p[1],p[3] ?? p[1])));
  const high = Math.max(10,...visible.map(p => Math.max(p[1],p[4] ?? p[1]))) * 1.08;
  const deltaRange = Math.max(10,...visible.map(p => Math.abs(p[5] ?? 0))) * 1.1;
  const x = p => left + (Date.parse(p[0])-start)/(now-start)*(right-left);
  const y = n => bottom-(n-low)/(high-low)*(bottom-top);
  const dy = n => (deltaTop+deltaBottom)/2-n/deltaRange*(deltaBottom-deltaTop)/2;
  const line = (segment,index,scale) => segment.map((p,i) => `${i ? "L":"M"}${x(p).toFixed(2)},${scale(p[index]).toFixed(2)}`).join(" ");
  const path = (segment,index,scale,cls) => `<path class="${cls}" d="${line(segment,index,scale)}"/>`;
  let content = `<title id="history-title">Published wait and difference from usual over ${hours} hours</title><desc id="history-description">Solid line: published wait. Shading: middle 50 percent of past published readings. Dashed line: historical median. Lower panel: difference in minutes. Gaps remain blank. An accessible data table follows.</desc>`;
  for (let i=0;i<=4;i++) {
    const value=low+(high-low)*i/4, yy=y(value);
    content+=`<line class="grid" x1="${left}" x2="${right}" y1="${yy}" y2="${yy}"/><text x="${left-8}" y="${yy+4}" text-anchor="end">${Math.round(value)}</text>`;
  }
  for (const value of [-deltaRange,0,deltaRange]) {
    const yy=dy(value);
    content+=`<line class="${value===0?"zero":"grid"}" x1="${left}" x2="${right}" y1="${yy}" y2="${yy}"/><text x="${left-8}" y="${yy+4}" text-anchor="end">${Math.round(value)}</text>`;
  }
  const tickCount=Math.max(2,Math.min(5,Math.floor((right-left)/120)));
  for (let i=0;i<tickCount;i++) {
    const time=new Date(start+(now-start)*i/(tickCount-1)), xx=left+(right-left)*i/(tickCount-1);
    const day=time.toLocaleDateString("en-US",{timeZone:"America/Chicago",month:"short",day:"numeric"});
    const hour=time.toLocaleTimeString("en-US",{timeZone:"America/Chicago",hour:"numeric",minute:"2-digit"});
    content+=`<text x="${xx}" y="${bottom+24}" text-anchor="${i===0?"start":i===tickCount-1?"end":"middle"}">${escape(day)}<tspan x="${xx}" dy="20">${escape(hour)}</tspan></text>`;
  }
  content+=`<text x="${left}" y="18">Published wait · min</text><text x="${left}" y="${deltaTop-15}">Difference from usual · min</text>`;
  const gap=policy.gap_seconds*1000;
  for (const s of segments(visible,p=>p[2]!==null,gap)) {
    const area=s.map(p=>`${x(p)},${y(p[3])}`).concat([...s].reverse().map(p=>`${x(p)},${y(p[4])}`)).join(" ");
    content+=`<polygon class="typical-band" points="${area}"/>`+path(s,2,y,"median-line")+path(s,5,dy,"delta-line");
  }
  for (const s of segments(visible,()=>true,gap)) content+=path(s,1,y,"wait-line");
  // Circles preserve isolated observations and expose an exact value on hover.
  for (const p of visible) content+=`<circle cx="${x(p)}" cy="${y(p[1])}" r="2" class="wait-point"><title>${escape(when(p[0]))}: ${p[1]} min; difference ${p[5]===null?"unavailable":signed(p[5])+" min"}</title></circle>`;
  const svg=`<svg viewBox="0 0 ${width} 480" role="img" aria-labelledby="history-title history-description">${content}</svg>` +
    `<p class="history-note" title="Prepared ${escape(when(generatedAt))}; newer live readings may be appended. Gaps over 20 minutes stay blank.">${visible.length} readings · America/Chicago</p>`;
  const table='<table><caption>Selected facility observations and past-only references</caption><thead><tr><th scope="col">Collected (Chicago)</th><th scope="col">Wait (min)</th><th scope="col">Median</th><th scope="col">Typical range</th><th scope="col">Difference (min)</th><th scope="col">Reference days</th><th scope="col">Coverage</th></tr></thead><tbody>' +
    [...visible].reverse().map(p=>`<tr><th scope="row">${escape(when(p[0]))}</th><td>${p[1]}</td><td>${fmt(p[2])}</td><td>${p[3]===null?"Insufficient history":fmt(p[3])+"–"+fmt(p[4])}</td><td>${p[5]===null?"Unavailable":signed(p[5])}</td><td>${p[7]}</td><td>${Math.round(p[8]*100)}%</td></tr>`).join("")+'</tbody></table>';
  return {svg,table,count:visible.length};
}
