// Live readings are fetched independently of Quarto. Never infer freshness from value changes.
const parseTime = value => typeof value === "string" && /T.*(Z|[+-]\d{2}:\d{2})$/.test(value)
  ? Date.parse(value) : NaN;
const escape = value => String(value).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

export function validateArtifact(data, expected) {
  if (data?.schema_version !== 1 || data.metric !== "CV_ED_Wait" || !Number.isFinite(parseTime(data.generated_at)) ||
      !Array.isArray(data.facilities) || data.facilities.length !== expected.length) throw Error("Invalid latest artifact");
  for (const key of ["stale_after_seconds", "refresh_seconds", "request_timeout_seconds", "expected_collection_seconds"]) {
    if (!Number.isSafeInteger(data.freshness?.[key]) || data.freshness[key] <= 0) throw Error("Invalid freshness policy");
  }
  const seen = new Set();
  for (const item of data.facilities) {
    if (!expected.some(f => f.slug === item.slug) || seen.has(item.slug) ||
        !["reporting", "failed", "missing"].includes(item.reporting_state)) throw Error("Invalid facility coverage");
    seen.add(item.slug);
    const observation = item.last_success;
    if (observation !== null && (!observation || observation.facility !== item.slug ||
        observation.metric !== data.metric || !Number.isSafeInteger(observation.wait_minutes) ||
        !Number.isSafeInteger(observation.latency_ms) || observation.latency_ms < 0 ||
        !Number.isFinite(parseTime(observation.observed_at)) || !Number.isFinite(parseTime(observation.batch_id)) ||
        parseTime(observation.batch_id) > parseTime(observation.observed_at) ||
        parseTime(observation.observed_at) > parseTime(data.generated_at))) throw Error("Invalid observation");
    const attempt = item.last_attempt;
    if (attempt !== null && (!attempt || !["success", "failed"].includes(attempt.state) ||
        !Number.isFinite(parseTime(attempt.attempted_at)) || !Number.isFinite(parseTime(attempt.batch_id)) ||
        parseTime(attempt.attempted_at) > parseTime(data.generated_at))) throw Error("Invalid attempt");
    const reporting = attempt?.state === "failed" ? "failed" : observation ? "reporting" : "missing";
    if (item.reporting_state !== reporting ||
        (reporting === "reporting" && attempt?.state !== "success")) throw Error("Inconsistent reporting state");
  }
  return data;
}

export function facilityView(item, artifact, now, refreshFailed = false) {
  const observation = item?.last_success;
  const age = observation ? (now - parseTime(observation.observed_at)) / 1000 : null;
  const artifactAge = artifact ? (now - parseTime(artifact.generated_at)) / 1000 : null;
  const labels = [];
  if (!observation) labels.push("Missing reading");
  else if (age < 0 || artifactAge < 0) labels.push("Clock mismatch");
  else if (age >= artifact.freshness.stale_after_seconds || artifactAge >= artifact.freshness.stale_after_seconds) labels.push("Stale");
  if (item?.last_attempt?.state === "failed") labels.push("Collection failed");
  if (refreshFailed) labels.push("Refresh failed");
  if (!labels.length) labels.push("Recently collected");
  return {value: observation?.wait_minutes ?? null, age, labels,
          current: labels.length === 1 && labels[0] === "Recently collected",
          observedAt: observation?.observed_at ?? null, attempt: item?.last_attempt ?? null};
}

export function renderCards(expected, artifact, now, refreshFailed) {
  const bySlug = new Map((artifact?.facilities ?? []).map(item => [item.slug, item]));
  return expected.map(f => {
    const view = facilityView(bySlug.get(f.slug), artifact, now, refreshFailed);
    const age = view.age === null ? "No successful observation" : view.age < 0 ? "Observation time is in the future" :
      `Collected ${Math.floor(view.age / 60)} min ago`;
    const absolute = view.observedAt ? new Date(view.observedAt).toLocaleString("en-US", {timeZone: "America/Chicago", timeZoneName: "short"}) : "";
    const attempted = view.attempt?.state === "failed" ? `<p>Latest collection attempt failed at ${escape(new Date(view.attempt.attempted_at).toLocaleString("en-US", {timeZone: "America/Chicago", timeZoneName: "short"}))}.</p>` : "";
    return `<article class="wait-card ${view.current ? "recent" : "unavailable"}"><h3>${escape(f.display_name)}</h3>` +
      `<p class="wait-status">${escape(view.labels.join(" · "))}</p>` +
      `<p class="wait-value">${view.value === null ? "Unavailable" : `${view.value} min`}</p>` +
      `<p>${view.current ? "Published wait" : "Last published reading"}</p>` +
      `<p>${escape(age)}<br><time>${escape(absolute)}</time></p>${attempted}</article>`;
  }).join("");
}

export function createFeed({url = "data/latest.json", expected, fetcher = globalThis.fetch,
                            now = () => Date.now(), onChange = () => {}}) {
  let artifact = null, refreshFailed = false, pending = false;
  const state = () => ({artifact, refreshFailed, html: renderCards(expected, artifact, now(), refreshFailed)});
  const emit = () => onChange(state());
  return {
    state, tick: emit,
    async refresh() {
      if (pending) return;
      pending = true;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), (artifact?.freshness.request_timeout_seconds ?? 10) * 1000);
      try {
        const response = await fetcher(url, {cache: "no-store", signal: controller.signal});
        if (!response.ok) throw Error(`HTTP ${response.status}`);
        const candidate = validateArtifact(await response.json(), expected);
        if (artifact && parseTime(candidate.generated_at) < parseTime(artifact.generated_at)) throw Error("Artifact moved backwards");
        artifact = candidate;
        refreshFailed = false;
      } catch {
        refreshFailed = true;
      } finally {
        clearTimeout(timeout);
        pending = false;
        emit();
      }
    }
  };
}
