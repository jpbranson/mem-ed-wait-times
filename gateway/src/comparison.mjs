// Route comparison logic for the Cloudflare gateway: a port of edwait/routing.py.
// Pure module (no Cloudflare imports) so the site's Node test suite can cover it.

export const ENDPOINT = "https://api.tomtom.com/maps/orbis/routing/routes/calculate";
export const USER_AGENT = "mem-ed-wait-times/0.3 (TomTom Routing gateway)";
// Road endpoints must land near the target. Campus centers can sit inside large
// grounds, so they get a wider snap distance than a reviewed entrance.
export const ARRIVAL_TOLERANCE_METERS = {entrance: 150, campus: 300};
export const ORIGIN_TOLERANCE_METERS = 250;
export const ROUTE_TTL_SECONDS = 300;
export const CONTEXT_TTL_MS = 7_200_000;

// Only bounded public codes, never keys, provider URLs, or response bodies.
export class GatewayError extends Error {}

export const coordinate = (v, limit) => typeof v === "number" && Number.isFinite(v) && Math.abs(v) <= limit;
const nonnegative = v => coordinate(v, 1e9) && v >= 0;
const stamp = v => typeof v === "string" && /T.*(Z|[+-]\d{2}:\d{2})$/.test(v) ? Date.parse(v) : NaN;
const unavailable = slug => ({slug, status: "unavailable", seconds: null, meters: null, traffic_delay_seconds: null});

export function validateOrigin(input) {
  if (!input || typeof input !== "object" || Array.isArray(input) ||
      Object.keys(input).sort().join() !== "age_group,latitude,longitude" ||
      !coordinate(input.latitude, 90) || !coordinate(input.longitude, 180)) throw new GatewayError("invalid_origin");
  if (!["adult", "child"].includes(input.age_group)) throw new GatewayError("invalid_age_group");
  return {latitude: input.latitude, longitude: input.longitude, age_group: input.age_group};
}

// Destinations come from the page's own published travel context, so the gateway and
// the page always compare the same eligible set with the same arrival points.
export function candidatesFrom(travel, group, now) {
  if (travel?.schema_version !== 1 || travel.method_version !== "travel-wait-v1" || !Array.isArray(travel.facilities))
    throw new GatewayError("routing_unavailable");
  const age = now - stamp(travel.generated_at);
  if (!(age >= 0 && age < CONTEXT_TTL_MS)) throw new GatewayError("routing_unavailable");
  const seen = new Set(), candidates = [];
  for (const f of travel.facilities) {
    if (typeof f?.slug !== "string" || !f.slug || seen.has(f.slug)) throw new GatewayError("routing_unavailable");
    seen.add(f.slug);
    if (f.eligibility?.[group] !== null) continue;
    const point = f.arrival_point;
    if (!Object.hasOwn(ARRIVAL_TOLERANCE_METERS, f.arrival) || !coordinate(point?.latitude, 90) || !coordinate(point?.longitude, 180))
      throw new GatewayError("routing_unavailable");
    candidates.push({slug: f.slug, kind: f.arrival, latitude: point.latitude, longitude: point.longitude});
  }
  if (!candidates.length) throw new GatewayError("no_verified_destinations");
  if (candidates.length > 20) throw new GatewayError("too_many_destinations");
  return candidates;
}

export function routeRequest(origin, candidate, departure, key, endpoint = ENDPOINT) {
  const body = {routePlanningLocations: {origin: {type: "Point", coordinates: [origin.longitude, origin.latitude]},
                                         destination: {type: "Point", coordinates: [candidate.longitude, candidate.latitude]}},
                traffic: "live", departureDateTime: departure, routeType: "fast", travelMode: "car", maxPathAlternativeRoutes: 0};
  return [endpoint, {method: "POST", redirect: "manual", body: JSON.stringify(body),
    headers: {"TomTom-Api-Key": key, "TomTom-Api-Version": "3", "Attributes": "routes.summary,routes.legs.path",
              "Content-Type": "application/json", "User-Agent": USER_AGENT}}];
}

export function separation(a, b) {
  if (!Array.isArray(a) || a.length !== 2 || !coordinate(a[0], 180) || !coordinate(a[1], 90)) throw new Error("Invalid road endpoint");
  const [lon1, lat1, lon2, lat2] = [...a, ...b].map(v => v * Math.PI / 180);
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}

export function parseRoute(payload, slug, origin, destination, tolerance = ARRIVAL_TOLERANCE_METERS.entrance) {
  const route = payload.routes[0], summary = route.summary;
  const seconds = summary.travelDurationInSeconds, meters = summary.lengthInMeters;
  const delay = summary.trafficDelayDurationInSeconds ?? null;
  if (!nonnegative(seconds) || !nonnegative(meters) || (delay !== null && (!nonnegative(delay) || delay > seconds)))
    throw new Error("Invalid route summary");
  if (route.legs.length !== 1) throw new Error("Unexpected route legs");
  const path = route.legs[0].path;
  if (path.type !== "LineString" || !Array.isArray(path.coordinates) || path.coordinates.length < 2) throw new Error("Missing route endpoints");
  if (separation(path.coordinates[0], origin) > ORIGIN_TOLERANCE_METERS || separation(path.coordinates.at(-1), destination) > tolerance)
    throw new Error("Route ends too far from origin or arrival point");
  // Keep only timing/distance data; geometry and origin never leave the gateway.
  // Zero/missing delay does not prove live traffic coverage on every road segment.
  return {slug, status: "ok", seconds, meters, traffic_delay_seconds: delay};
}

// Individual Routing API calls (never TomTom's Matrix API): four workers, at most four
// starts per second, one comparison deadline, no retries. 401/403/429 stop new calls.
export async function compareRoutes({origin, candidates, key, departure, fetcher, clock, sleep, endpoint = ENDPOINT,
                                     deadlineMs = 15000, spacingMs = 250, workers = 4, requestTimeoutMs = 7000}) {
  const deadline = clock() + deadlineMs, start = [origin.longitude, origin.latitude];
  const routes = new Array(candidates.length), fatal = [];
  let queue = Promise.resolve(), last = -Infinity, stopped = false, next = 0;
  // Grants are serialized and anchored to the actual grant time, like the Python lock.
  // Timers can fire early, so wait until the clock itself reaches the slot.
  function slot() {
    const turn = queue.then(async () => {
      if (stopped || Math.max(clock(), last + spacingMs) >= deadline) return false;
      for (let wait, before; (wait = last + spacingMs - clock()) > 0;) {
        before = clock();
        await sleep(wait);
        if (clock() <= before) break;  // A clock that never advances cannot be waited on.
      }
      if (stopped) return false;
      last = clock();
      return true;
    });
    queue = turn.catch(() => false);
    return turn;
  }
  async function calculate(candidate) {
    if (!await slot()) return unavailable(candidate.slug);
    const remaining = deadline - clock();
    if (remaining <= 100) return unavailable(candidate.slug);
    const [url, init] = routeRequest(origin, candidate, departure, key, endpoint);
    try {
      const response = await fetcher(url, {...init, signal: AbortSignal.timeout(Math.min(requestTimeoutMs, remaining))});
      if (response.status !== 200) {
        if ([401, 403, 429].includes(response.status)) {
          fatal.push(response.status === 429 ? "provider_limit_reached" : "routing_access_denied");
          stopped = true;
        }
        try { await response.body?.cancel(); } catch { /* Connection cleanup only. */ }
        return unavailable(candidate.slug);
      }
      const route = parseRoute(await response.json(), candidate.slug, start, [candidate.longitude, candidate.latitude],
                               ARRIVAL_TOLERANCE_METERS[candidate.kind]);
      return clock() <= deadline ? route : unavailable(candidate.slug);
    } catch { return unavailable(candidate.slug); }
  }
  async function worker() {
    while (next < candidates.length) { const i = next++; routes[i] = await calculate(candidates[i]); }
  }
  await Promise.all(Array.from({length: Math.min(workers, candidates.length)}, worker));
  return {routes, fatal};
}

export function responseBody(group, generatedAt, routes) {
  return {schema_version: 2, provider: "tomtom", traffic_mode: "live", generated_at: generatedAt,
          ttl_seconds: ROUTE_TTL_SECONDS, age_group: group, routes};
}
