import test from "node:test";
import assert from "node:assert/strict";
import {ENDPOINT, GatewayError, candidatesFrom, compareRoutes, parseRoute, validateOrigin} from "../gateway/src/comparison.mjs";
import {RouteGateCore, budgetLimit, endpointFrom} from "../gateway/src/gate.mjs";
import {handle, statusFor} from "../gateway/src/handler.mjs";
import {eligible, validateRoutes} from "../dashboard/travel.mjs";

let sqlite = null;
try { sqlite = await import("node:sqlite"); } catch { /* Ledger tests need Node 22.13+. */ }

const at = "2026-09-14T17:00:00Z", now = Date.parse(at), DAY = 86_400_000;
const KEY = "test-only-key-must-not-escape";
const ORIGIN = {latitude: 35.15, longitude: -90.05, age_group: "adult"};
const movement = () => [15, 30, 60, 120].map(h => ({horizon_minutes: h, pairs: 500, days: 10, absolute_change_p90: 5}));

// Synthetic context and coordinates, never real destinations.
function travel() {
  return {schema_version: 1, method_version: "travel-wait-v1", metric: "CV_ED_Wait", generated_at: at,
    recommendations_enabled: false, policy: {route_ttl_seconds: 300, context_ttl_seconds: 7200, meaningful_minutes: 10},
    facilities: [
      {slug: "a", display_name: "Example A", eligibility: {adult: null, child: "Unverified"}, arrival: "entrance",
       arrival_point: {latitude: 35.14, longitude: -90.04}, movement: movement()},
      {slug: "b", display_name: "Example B", eligibility: {adult: null, child: null}, arrival: "campus",
       arrival_point: {latitude: 35.13, longitude: -90.02}, movement: movement()},
      {slug: "c", display_name: "Example C", eligibility: {adult: "Active emergency service unverified", child: "Unverified"},
       arrival: "campus", arrival_point: {latitude: 35.2, longitude: -90.1}, movement: movement()}]};
}

function payload(origin = [-90.05, 35.15], destination = [-90.04, 35.14], summary = {}) {
  return {routes: [{summary: {lengthInMeters: 2058, travelDurationInSeconds: 600, trafficDelayDurationInSeconds: 60, ...summary},
                    legs: [{path: {type: "LineString", coordinates: [origin, destination]}}]}]};
}

function clock() {
  const c = {value: now};
  c.now = () => c.value;
  c.sleep = async ms => { c.value += ms; };
  return c;
}

// Serves the travel context and echoes a valid route to each requested destination.
function provider({context = travel(), status = () => 200, onRoute = () => {}} = {}) {
  const calls = [], routes = [];
  const fetcher = async (url, init) => {
    calls.push({url: String(url), init});
    if (String(url).endsWith("/travel.json")) return context instanceof Response ? context : Response.json(context);
    const points = JSON.parse(init.body).routePlanningLocations;
    routes.push({url: String(url), init});
    await onRoute(points);
    const code = status(points.destination.coordinates);
    if (code !== 200) return new Response(JSON.stringify({detail: KEY}), {status: code});
    return Response.json(payload(points.origin.coordinates, points.destination.coordinates));
  };
  return {fetcher, calls, routes};
}

function storage() {
  const db = new sqlite.DatabaseSync(":memory:");
  const sql = {exec(query, ...params) {
    const statement = db.prepare(query);
    const rows = /^\s*select/i.test(query) ? statement.all(...params) : (statement.run(...params), []);
    return {toArray: () => rows};
  }};
  const transaction = fn => {
    db.exec("BEGIN IMMEDIATE");
    try { const result = fn(); db.exec("COMMIT"); return result; } catch (error) { db.exec("ROLLBACK"); throw error; }
  };
  return {db, sql, transaction};
}

function gate({env = {}, store = storage(), time = clock(), ...options} = {}) {
  const fake = provider(options);
  const core = new RouteGateCore({sql: store.sql, transaction: store.transaction, fetcher: fake.fetcher,
    clock: time.now, sleep: time.sleep,
    env: {TOMTOM_API_KEY: KEY, ASSET_ORIGIN: "https://assets.example", TOMTOM_REQUEST_BUDGET: "20", ...env}});
  return {core, store, time, ...fake};
}

const code = fn => { try { fn(); } catch (error) { assert.ok(error instanceof GatewayError); return error.message; } assert.fail("Expected a gateway error"); };

test("origin validation mirrors the local gateway", () => {
  assert.deepEqual(validateOrigin({...ORIGIN}), ORIGIN);
  for (const patch of [{latitude: true}, {latitude: 91}, {longitude: -181}, {longitude: "1"}, {destinations: [ORIGIN]}])
    assert.equal(code(() => validateOrigin({...ORIGIN, ...patch})), "invalid_origin");
  for (const input of [null, [], "x", {latitude: 1, longitude: 1}]) assert.equal(code(() => validateOrigin(input)), "invalid_origin");
  assert.equal(code(() => validateOrigin({...ORIGIN, age_group: "unknown"})), "invalid_age_group");
});

test("destinations come only from a current published travel context", () => {
  assert.deepEqual(candidatesFrom(travel(), "adult", now), [
    {slug: "a", kind: "entrance", latitude: 35.14, longitude: -90.04},
    {slug: "b", kind: "campus", latitude: 35.13, longitude: -90.02}]);
  assert.deepEqual(candidatesFrom(travel(), "child", now).map(c => c.slug), ["b"]);
  assert.equal(candidatesFrom(travel(), "adult", now + 7_199_999).length, 2);
  const broken = [c => c.generated_at = "2026-09-14T15:00:00Z", c => c.generated_at = "2026-09-14T17:00:01Z",
    c => c.generated_at = "2026-09-14 17:00", c => c.schema_version = 2, c => c.method_version = "other", c => c.facilities = null,
    c => c.facilities[1].slug = "a", c => delete c.facilities[0].arrival_point, c => c.facilities[0].arrival = null,
    c => c.facilities[0].arrival_point.latitude = 91];
  for (const patch of broken) { const c = travel(); patch(c); assert.equal(code(() => candidatesFrom(c, "adult", now)), "routing_unavailable"); }
  const none = travel(); none.facilities.forEach(f => f.eligibility.adult = "Unverified");
  assert.equal(code(() => candidatesFrom(none, "adult", now)), "no_verified_destinations");
  const many = travel(); many.facilities = Array.from({length: 21}, (_, i) => ({...travel().facilities[0], slug: `f${i}`}));
  assert.equal(code(() => candidatesFrom(many, "adult", now)), "too_many_destinations");
});

test("routes are individual live-traffic POSTs with the key only in a header", async () => {
  const fake = provider(), time = clock();
  const {routes, fatal} = await compareRoutes({origin: ORIGIN, candidates: candidatesFrom(travel(), "adult", now), key: KEY,
    departure: at, fetcher: fake.fetcher, clock: time.now, sleep: time.sleep});
  assert.deepEqual(fatal, []);
  assert.equal(fake.routes.length, 2);
  for (const {url, init} of fake.routes) {
    assert.equal(url, ENDPOINT);
    assert.ok(!url.includes(KEY) && !url.includes("35.15"));
    assert.equal(init.method, "POST");
    assert.equal(init.redirect, "manual");
    assert.ok(init.signal instanceof AbortSignal);
    assert.equal(init.headers["TomTom-Api-Key"], KEY);
    assert.equal(init.headers["TomTom-Api-Version"], "3");
    assert.equal(init.headers.Attributes, "routes.summary,routes.legs.path");
    const body = JSON.parse(init.body);
    assert.deepEqual([body.traffic, body.departureDateTime, body.routeType, body.travelMode, body.maxPathAlternativeRoutes],
                     ["live", at, "fast", "car", 0]);
    assert.deepEqual(body.routePlanningLocations.origin.coordinates, [-90.05, 35.15]);
  }
  assert.deepEqual(JSON.parse(fake.routes[1].init.body).routePlanningLocations.destination.coordinates, [-90.02, 35.13]);
  assert.deepEqual(routes[0], {slug: "a", status: "ok", seconds: 600, meters: 2058, traffic_delay_seconds: 60});
});

test("route parsing keeps delay semantics and fails closed like the Python adapter", () => {
  const origin = [-90.05, 35.15], destination = [-90.04, 35.14];
  const missing = payload(); delete missing.routes[0].summary.trafficDelayDurationInSeconds;
  assert.equal(parseRoute(missing, "t", origin, destination).traffic_delay_seconds, null);
  assert.equal(parseRoute(payload(origin, destination, {trafficDelayDurationInSeconds: 0}), "t", origin, destination).traffic_delay_seconds, 0);
  for (const field of ["travelDurationInSeconds", "lengthInMeters", "trafficDelayDurationInSeconds"])
    for (const value of [-1, NaN, true, "600"])
      assert.throws(() => parseRoute(payload(origin, destination, {[field]: value}), "t", origin, destination));
  assert.throws(() => parseRoute(payload(origin, destination, {trafficDelayDurationInSeconds: 601}), "t", origin, destination));
  assert.throws(() => parseRoute(payload([0, 0]), "t", origin, destination));
  assert.throws(() => parseRoute(payload(origin, [0, 0]), "t", origin, destination));
  assert.throws(() => parseRoute({routes: []}, "t", origin, destination));
  // About 250 m north of the target: plausible for a large campus, not for an entrance.
  const near = payload(origin, [-90.04, 35.14225]);
  assert.equal(parseRoute(near, "campus", origin, destination, 300).status, "ok");
  assert.throws(() => parseRoute(near, "entrance", origin, destination));
});

test("starts are spaced, the deadline holds, failures stay partial, and quota errors stop new calls", async () => {
  const many = Array.from({length: 6}, (_, i) => ({slug: `f${i}`, kind: "campus", latitude: 35.14, longitude: -90.04 - i / 100}));
  // Real timers: concurrent sleeps overlap, so a shared fake clock would overstate spacing.
  const starts = [], spaced = provider({onRoute: () => starts.push(performance.now())});
  await compareRoutes({origin: ORIGIN, candidates: many, key: KEY, departure: at, fetcher: spaced.fetcher, spacingMs: 30,
    clock: () => performance.now(), sleep: ms => new Promise(resolve => setTimeout(resolve, ms))});
  assert.equal(starts.length, 6);
  starts.slice(1).forEach((t, i) => assert.ok(t - starts[i] >= 28, `${t - starts[i]} ms between starts`));

  let time = clock();
  const slow = provider({onRoute: () => { time.value += 16_000; }});
  let result = await compareRoutes({origin: ORIGIN, candidates: many, key: KEY, departure: at, fetcher: slow.fetcher, clock: time.now, sleep: time.sleep});
  assert.ok(result.routes.every(r => r.status === "unavailable"));
  assert.ok(slow.routes.length <= 4);

  time = clock();
  const partial = provider({onRoute: points => { if (points.destination.coordinates[0] === -90.04) throw new Error(KEY); }});
  result = await compareRoutes({origin: ORIGIN, candidates: many.slice(0, 2), key: KEY, departure: at, fetcher: partial.fetcher, clock: time.now, sleep: time.sleep});
  assert.deepEqual(result.routes.map(r => r.status), ["unavailable", "ok"]);
  assert.ok(!JSON.stringify(result).includes(KEY));

  for (const [status, expected] of [[401, "routing_access_denied"], [403, "routing_access_denied"], [429, "provider_limit_reached"]]) {
    time = clock();
    const denied = provider({status: () => status});
    result = await compareRoutes({origin: ORIGIN, candidates: many, key: KEY, departure: at, fetcher: denied.fetcher, clock: time.now, sleep: time.sleep, workers: 1});
    assert.deepEqual(result.fatal, [expected]);
    assert.equal(denied.routes.length, 1);
  }
});

test("budget, gate and endpoint configuration fail closed", () => {
  assert.equal(budgetLimit(undefined), 20000);
  assert.equal(budgetLimit(" 25 "), 25);
  for (const bad of ["0", "20001", "1e3", "-1", "2.5", "abc"]) assert.equal(code(() => budgetLimit(bad)), "request_budget_unavailable");
  assert.equal(endpointFrom(undefined), ENDPOINT);
  assert.equal(endpointFrom("http://127.0.0.1:9999/calculate"), "http://127.0.0.1:9999/calculate");
  for (const bad of ["https://evil.example/calculate", "http://example.com/", "https://127.0.0.1/", "not a url"])
    assert.equal(code(() => endpointFrom(bad)), "routing_not_configured");
});

test("a comparison reserves its whole set first, persists usage, and stores no locations", {skip: !sqlite}, async () => {
  const store = storage();
  const first = gate({store, env: {TOMTOM_REQUEST_BUDGET: "3"}});
  const result = await first.core.compare({...ORIGIN});
  assert.equal(result.ok, true);
  assert.doesNotThrow(() => validateRoutes(result.body, eligible(travel(), "adult"), "adult"));
  assert.equal(result.body.generated_at, new Date(now).toISOString());
  assert.ok(!JSON.stringify(result).includes(KEY) && !JSON.stringify(result).includes("coordinates"));
  // A fresh object instance sees the same ledger, as after a redeploy or eviction.
  const second = gate({store, env: {TOMTOM_REQUEST_BUDGET: "3"}});
  assert.deepEqual(await second.core.compare({...ORIGIN}), {ok: false, code: "request_budget_exhausted"});
  assert.equal(second.routes.length, 0);
  assert.deepEqual(store.db.prepare("SELECT day, calls FROM requests").all().map(r => ({...r})), [{day: "2026-09-14", calls: 2}]);
  assert.deepEqual(store.db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").all().map(r => r.name), ["requests", "state"]);
});

test("the ledger rolls over 32 UTC dates and a clock rollback keeps newer reservations", {skip: !sqlite}, () => {
  const {core} = gate({env: {TOMTOM_REQUEST_BUDGET: "2"}});
  core.reserve(2, now);
  assert.equal(code(() => core.reserve(1, now + 31 * DAY)), "request_budget_exhausted");
  core.reserve(2, now + 32 * DAY);
  assert.equal(code(() => core.reserve(1, now)), "request_budget_exhausted");
  const broken = gate({env: {TOMTOM_REQUEST_BUDGET: "2"}});
  broken.core.sql = {exec() { throw new Error("disk"); }};
  assert.equal(code(() => broken.core.reserve(1, now)), "request_budget_unavailable");
});

test("missing configuration, context or storage spends nothing", {skip: !sqlite}, async () => {
  let g = gate({env: {TOMTOM_API_KEY: " "}});
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "routing_not_configured"});
  assert.equal(g.calls.length, 0);
  g = gate({env: {TOMTOM_ENDPOINT: "https://evil.example/"}});
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "routing_not_configured"});
  assert.equal(g.calls.length, 0);
  g = gate({context: new Response("missing", {status: 404})});
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "routing_unavailable"});
  assert.equal(g.routes.length, 0);
  assert.deepEqual(g.store.db.prepare("SELECT name FROM sqlite_master WHERE name = 'requests'").all(), []);
  g = gate({env: {TOMTOM_REQUEST_BUDGET: "abc"}});
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "request_budget_unavailable"});
  assert.equal(g.routes.length, 0);
  g = gate();
  g.core.sql = {exec() { throw new Error("disk"); }};
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "request_budget_unavailable"});
  assert.equal(g.calls.length, 0);
  g = gate();
  assert.deepEqual(await g.core.compare({...ORIGIN, age_group: "senior"}), {ok: false, code: "invalid_age_group"});
  assert.equal(g.calls.length, 0);
});

test("only one comparison runs at a time", {skip: !sqlite}, async () => {
  let release;
  const held = new Promise(resolve => { release = resolve; });
  const g = gate({onRoute: () => held});
  const first = g.core.compare({...ORIGIN});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "rate_limited"});
  release();
  assert.equal((await first).ok, true);
  assert.equal((await g.core.compare({...ORIGIN})).ok, true);
});

test("auth and quota errors cool down across instances; other provider errors do not", {skip: !sqlite}, async () => {
  for (const [status, expected] of [[429, "provider_limit_reached"], [401, "routing_access_denied"]]) {
    const store = storage(), time = clock();
    const failing = gate({store, time, status: () => status});
    assert.deepEqual(await failing.core.compare({...ORIGIN}), {ok: false, code: expected});
    const retry = gate({store, time});
    assert.deepEqual(await retry.core.compare({...ORIGIN}), {ok: false, code: "provider_limit_reached"});
    assert.equal(retry.routes.length, 0);
    time.value += 60_000;
    assert.equal((await retry.core.compare({...ORIGIN})).ok, true);
  }
  const g = gate({status: () => 500});
  assert.deepEqual(await g.core.compare({...ORIGIN}), {ok: false, code: "routing_unavailable"});
  assert.equal((await gate({store: g.store}).core.compare({...ORIGIN})).ok, true);
});

function post(body, headers = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return new Request("https://gateway.example/api/routes", {method: "POST", body: text,
    headers: {Origin: "https://gateway.example", "Content-Type": "application/json", "Content-Length": String(new TextEncoder().encode(text).length), ...headers}});
}

test("the HTTP boundary enforces origin, size and error mapping without leaking details", async () => {
  const seen = [];
  const env = {TOMTOM_API_KEY: KEY, ASSET_ORIGIN: "https://assets.example"};
  const ok = {compare: async input => { seen.push(input); return {ok: true, body: {schema_version: 2}}; }};
  let response = await handle(post(ORIGIN), env, {gate: ok});
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(seen, [ORIGIN]);
  for (const request of [post(ORIGIN, {Origin: "https://evil.example"}), post(ORIGIN, {Origin: ""})])
    assert.equal((await handle(request, env, {gate: ok})).status, 403);
  for (const request of [post("x".repeat(513)), post(ORIGIN, {"Content-Type": "text/plain"}), post("{"), post(ORIGIN, {"Content-Length": "0"})]) {
    response = await handle(request, env, {gate: ok});
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), {error: "invalid_request"});
  }
  assert.equal(seen.length, 1);
  for (const [error, status] of [["rate_limited", 429], ["request_budget_exhausted", 429], ["routing_not_configured", 503],
                                 ["routing_access_denied", 503], ["invalid_origin", 422], ["no_verified_destinations", 422]]) {
    response = await handle(post(ORIGIN), env, {gate: {compare: async () => ({ok: false, code: error})}});
    assert.equal(response.status, status);
    assert.equal(statusFor(error), status);
    assert.deepEqual(await response.json(), {error});
  }
  response = await handle(post(ORIGIN), env, {gate: {compare: async () => { throw new Error(KEY); }}});
  assert.equal(response.status, 503);
  assert.ok(!(await response.text()).includes(KEY));
  assert.equal((await handle(new Request("https://gateway.example/api/routes"), env, {gate: ok})).status, 405);
  assert.equal((await handle(new Request("https://gateway.example/api/other"), env, {gate: ok})).status, 404);
});

test("the status probe reports configuration only", async () => {
  for (const [key, available] of [[KEY, true], ["", false], [undefined, false]]) {
    const response = await handle(new Request("https://gateway.example/api/routes/status"), {TOMTOM_API_KEY: key}, {gate: null});
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    const text = await response.text();
    assert.deepEqual(JSON.parse(text), {schema_version: 1, available});
    assert.ok(!text.includes(KEY));
  }
});

test("static assets pass through from the bucket without query strings, cookies or bucket headers", async () => {
  const requests = [];
  const fetcher = async (url, init) => {
    requests.push({url: String(url), init});
    return new Response("<html></html>", {status: 200, headers: {"Content-Type": "text/html", "Cache-Control": "no-store",
      ETag: '"abc"', "x-amz-request-id": "hidden", Server: "AmazonS3"}});
  };
  const env = {ASSET_ORIGIN: "https://bucket.example"};
  const response = await handle(new Request("https://gateway.example/?utm=1", {headers: {Cookie: "secret", "If-None-Match": '"abc"'}}), env, {gate: null, fetcher});
  assert.equal(requests[0].url, "https://bucket.example/index.html");
  assert.equal(requests[0].init.headers.get("If-None-Match"), '"abc"');
  assert.equal(requests[0].init.headers.get("Cookie"), null);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal(response.headers.get("ETag"), '"abc"');
  assert.equal(response.headers.get("x-amz-request-id"), null);
  assert.equal(response.headers.get("Server"), null);
  assert.equal(requests[0].init.cache, "no-store");  // Never an edge copy from an earlier build.
  const uncached = await handle(new Request("https://gateway.example/latest.css"), env,
    {gate: null, fetcher: async () => new Response("a{}", {headers: {"Content-Type": "text/css", ETag: '"css"'}})});
  assert.equal(uncached.headers.get("Cache-Control"), "no-cache");
  await handle(new Request("https://gateway.example/data/latest.json?t=5"), env, {gate: null, fetcher});
  assert.equal(requests[1].url, "https://bucket.example/data/latest.json");
  assert.equal((await handle(new Request("https://gateway.example/index.html", {method: "POST", body: "x"}), env, {gate: null, fetcher})).status, 405);
  const down = await handle(new Request("https://gateway.example/app.mjs"), env, {gate: null, fetcher: async () => { throw new Error("offline"); }});
  assert.equal(down.status, 502);
});
