// End-to-end check of the gateway in Cloudflare's local runtime (wrangler dev / workerd).
// Serves the locally built dashboard as the asset origin and a loopback mock of TomTom,
// so nothing reaches TomTom unless --live is given. Usage (from gateway/):
//   node scripts/local-check.mjs            full mock check, report in ../.cache/
//   node scripts/local-check.mjs --serve    keep the mock-backed gateway running for a browser
//   node scripts/local-check.mjs --live     one real comparison from a fixed public point,
//                                           key read by wrangler from ../.env.local
import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdir, mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
import {createServer} from "node:http";
import {tmpdir} from "node:os";
import {extname, join, normalize, resolve, sep} from "node:path";
import {fileURLToPath} from "node:url";
import {availableContext, eligible, validateRoutes, validateTravel} from "../../dashboard/travel.mjs";
import {separation} from "../src/comparison.mjs";

const here = fileURLToPath(new URL("..", import.meta.url));
const root = resolve(here, "..");
const site = join(root, "dashboard", "_site");
const PUBLIC = "https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/";
// Downtown Memphis road point used by scripts/check_routes.py: public, never a user location.
const ORIGIN = {latitude: 35.1495, longitude: -90.049};
const MOCK_KEY = "local-check-key";
const TYPES = {".html": "text/html; charset=utf-8", ".mjs": "text/javascript", ".js": "text/javascript",
  ".json": "application/json", ".css": "text/css", ".woff2": "font/woff2", ".svg": "image/svg+xml",
  ".png": "image/png", ".txt": "text/plain; charset=utf-8", ".map": "application/json"};
const args = new Set(process.argv.slice(2));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function listen(handler, port = 0) {
  return new Promise(resolve => { const server = createServer(handler); server.listen(port, "127.0.0.1", () => resolve(server)); });
}
async function freePort() {
  const server = await listen(() => {});
  const {port} = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}

const expected = JSON.parse(await readFile(join(root, "edwait", "facilities.json"), "utf8")).facilities;
const travel = validateTravel(JSON.parse(await readFile(join(site, "travel.json"), "utf8")), expected);
if (!availableContext(travel, Date.now()) || !travel.facilities.every(f => "arrival_point" in f)) {
  console.error("dashboard/_site/travel.json is missing arrival points or older than two hours: run " +
    "`python -m edwait.prepare` and `quarto render dashboard/ --to html` first.");
  process.exit(2);
}

// The built site stands in for the S3 bucket; latest readings come from the public copy.
const assets = await listen(async (request, response) => {
  const path = decodeURIComponent(new URL(request.url, "http://local").pathname);
  if (path === "/data/latest.json") {
    const upstream = await fetch(PUBLIC + "data/latest.json", {cache: "no-store"});
    response.writeHead(upstream.status, {"Content-Type": "application/json", "Cache-Control": "no-store"});
    return response.end(await upstream.text());
  }
  const file = normalize(join(site, path === "/" ? "index.html" : path));
  if (!file.startsWith(site + sep)) { response.writeHead(403); return response.end(); }
  try {
    const body = await readFile(file);
    response.writeHead(200, {"Content-Type": TYPES[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-cache"});
    response.end(request.method === "HEAD" ? undefined : body);
  } catch { response.writeHead(404); response.end(); }
});

// Loopback TomTom stand-in: echoes a straight "route" to whatever destination is asked for.
const mock = {status: 200, delayMs: 0, starts: [], keys: new Set()};
const tomtom = await listen((request, response) => {
  let body = "";
  response.on("error", () => {});
  request.on("data", chunk => { body += chunk; });
  request.on("end", async () => {
    mock.starts.push(performance.now());
    mock.keys.add(request.headers["tomtom-api-key"]);
    if (mock.delayMs) await sleep(mock.delayMs);
    if (mock.status !== 200) { response.writeHead(mock.status, {"Content-Type": "application/json"}); return response.end("{}"); }
    const points = JSON.parse(body).routePlanningLocations;
    const [a, b] = [points.origin.coordinates, points.destination.coordinates];
    const meters = Math.round(separation(a, b) * 1.3);
    response.writeHead(200, {"Content-Type": "application/json"});
    response.end(JSON.stringify({routes: [{summary: {lengthInMeters: meters, travelDurationInSeconds: Math.round(meters / 13.4),
      trafficDelayDurationInSeconds: 0}, legs: [{path: {type: "LineString", coordinates: [a, b]}}]}]}));
  });
});

const persist = await mkdtemp(join(tmpdir(), "gateway-state-"));
const wranglerBin = join(here, "node_modules", "wrangler", "bin", "wrangler.js");
const assetOrigin = `http://127.0.0.1:${assets.address().port}`;
const endpoint = `http://127.0.0.1:${tomtom.address().port}/maps/orbis/routing/routes/calculate`;

async function start(vars, envFiles = []) {
  const port = await freePort(), inspector = await freePort();
  const argv = [wranglerBin, "dev", "--ip", "127.0.0.1", "--port", String(port), "--inspector-port", String(inspector),
    "--persist-to", persist, "--show-interactive-dev-session=false", "--log-level", "warn",
    ...Object.entries(vars).flatMap(([name, value]) => ["--var", `${name}:${value}`]), ...envFiles.flatMap(f => ["--env-file", f])];
  const child = spawn(process.execPath, argv, {cwd: here, env: {...process.env, WRANGLER_SEND_METRICS: "false"}, stdio: ["ignore", "pipe", "pipe"]});
  let output = "";
  child.stdout.on("data", d => { output += d; });
  child.stderr.on("data", d => { output += d; });
  const base = `http://127.0.0.1:${port}`;
  for (const began = Date.now(); Date.now() - began < 90_000; await sleep(500)) {
    if (child.exitCode !== null) throw new Error("wrangler exited:\n" + output.slice(-3000));
    try { if ((await fetch(base + "/api/routes/status")).ok) return {child, base, output: () => output}; } catch { /* Not ready. */ }
  }
  await stop({child});
  throw new Error("wrangler did not become ready:\n" + output.slice(-3000));
}

async function stop(worker) {
  if (worker.child.exitCode !== null) return;
  const exited = new Promise(resolve => worker.child.once("exit", resolve));
  // workerd runs as a grandchild; on Windows only a tree kill releases its port.
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(worker.child.pid), "/T", "/F"], {stdio: "ignore"});
  else worker.child.kill("SIGINT");
  await exited;
}

async function compare(worker, extra = {}, group = "adult") {
  const body = JSON.stringify({...ORIGIN, age_group: group});
  const response = await fetch(worker.base + "/api/routes", {method: "POST", body,
    headers: {Origin: worker.base, "Content-Type": "application/json", ...extra}});
  return {status: response.status, data: await response.json()};
}

const results = [];
async function check(name, fn) {
  try { const detail = await fn(); results.push({name, status: "passed", ...(detail ? {detail} : {})}); }
  catch (error) { results.push({name, status: "failed", error: String(error.message ?? error).slice(0, 800)}); }
}

const adults = eligible(travel, "adult").length;
let worker = null;
try {
  if (args.has("--serve")) {
    worker = await start(args.has("--live") ? {ASSET_ORIGIN: assetOrigin, TOMTOM_REQUEST_BUDGET: "60"} :
      {ASSET_ORIGIN: assetOrigin, TOMTOM_ENDPOINT: endpoint, TOMTOM_API_KEY: MOCK_KEY, TOMTOM_REQUEST_BUDGET: "2000"},
      args.has("--live") ? [join(root, ".env.local")] : []);
    console.log(`Gateway (${args.has("--live") ? "LIVE TomTom" : "mock TomTom"}) at ${worker.base}/ — Ctrl+C to stop (pid ${process.pid})`);
    await new Promise(resolve => process.once("SIGINT", resolve));
  } else if (args.has("--live")) {
    // One comparison: `adults` real Routing requests, reserved in this run's local ledger.
    worker = await start({ASSET_ORIGIN: assetOrigin, TOMTOM_REQUEST_BUDGET: String(adults)}, [join(root, ".env.local")]);
    await check("live comparison through workerd", async () => {
      const began = performance.now(), {status, data} = await compare(worker), elapsed = performance.now() - began;
      assert.equal(status, 200, JSON.stringify(data));
      validateRoutes(data, eligible(travel, "adult"), "adult");
      const ok = data.routes.filter(r => r.status === "ok"), minutes = ok.map(r => r.seconds / 60).sort((a, b) => a - b);
      return {checked_at: new Date().toISOString(), generated_at: data.generated_at, destinations: data.routes.length, ok: ok.length,
        elapsed_seconds: +(elapsed / 1000).toFixed(1), drive_minutes: {min: +minutes[0].toFixed(1),
        median: +minutes[Math.floor(minutes.length / 2)].toFixed(1), max: +minutes.at(-1).toFixed(1)},
        reported_delay: ok.filter(r => r.traffic_delay_seconds > 0).length, unknown_delay: ok.filter(r => r.traffic_delay_seconds === null).length};
    });
  } else {
    worker = await start({ASSET_ORIGIN: assetOrigin, TOMTOM_ENDPOINT: endpoint, TOMTOM_API_KEY: MOCK_KEY, TOMTOM_REQUEST_BUDGET: String(2 * adults + 4)});
    await check("dashboard pages pass through with bucket cache headers", async () => {
      const page = await fetch(worker.base + "/?x=1");
      assert.equal(page.status, 200);
      assert.match(page.headers.get("content-type"), /text\/html/);
      assert.match(await page.text(), /Drive \+ wait/);
      const latest = await fetch(worker.base + "/data/latest.json");
      assert.equal(latest.status, 200);
      assert.equal(latest.headers.get("cache-control"), "no-store");
      assert.equal((await fetch(worker.base + "/missing.txt")).status, 404);
    });
    await check("status probe", async () => {
      const response = await fetch(worker.base + "/api/routes/status");
      assert.equal(response.headers.get("cache-control"), "no-store");
      assert.deepEqual(await response.json(), {schema_version: 1, available: true});
    });
    await check("comparison matches the page's eligible set and spaces provider starts", async () => {
      mock.starts.length = 0;
      const {status, data} = await compare(worker);
      assert.equal(status, 200, JSON.stringify(data));
      validateRoutes(data, eligible(travel, "adult"), "adult");
      assert.equal(data.routes.filter(r => r.status === "ok").length, adults);
      assert.deepEqual([...mock.keys], [MOCK_KEY]);
      const gaps = mock.starts.slice(1).map((t, i) => t - mock.starts[i]).sort((a, b) => a - b);
      assert.ok(gaps[0] >= 240, `closest provider starts ${gaps[0].toFixed(1)} ms apart`);
      return {destinations: data.routes.length, min_start_gap_ms: +gaps[0].toFixed(1)};
    });
    await check("child group uses its own eligible set", async () => {
      const {status, data} = await compare(worker, {}, "child");
      assert.equal(status, 200, JSON.stringify(data));
      validateRoutes(data, eligible(travel, "child"), "child");
      return {destinations: data.routes.length};
    });
    await check("boundary rejections", async () => {
      assert.equal((await compare(worker, {Origin: "https://evil.example"})).status, 403);
      const big = await fetch(worker.base + "/api/routes", {method: "POST", body: "x".repeat(600),
        headers: {Origin: worker.base, "Content-Type": "application/json"}});
      assert.equal(big.status, 400);
      assert.equal((await fetch(worker.base + "/api/routes")).status, 405);
      assert.equal((await fetch(worker.base + "/api/other")).status, 404);
    });
    await check("concurrent comparisons are serialized", async () => {
      mock.delayMs = 300;
      const answers = await Promise.all([0, 1, 2].map(() => compare(worker)));
      mock.delayMs = 0;
      assert.deepEqual(answers.map(a => a.status).sort(), [200, 429, 429]);
      assert.ok(answers.filter(a => a.status === 429).every(a => a.data.error === "rate_limited"));
    });
    await check("ledger exhaustion stops before provider calls", async () => {
      const before = mock.starts.length, {status, data} = await compare(worker);
      assert.deepEqual([status, data], [429, {error: "request_budget_exhausted"}]);
      assert.equal(mock.starts.length, before);
    });
    await stop(worker);
    worker = await start({ASSET_ORIGIN: assetOrigin, TOMTOM_ENDPOINT: endpoint, TOMTOM_API_KEY: MOCK_KEY, TOMTOM_REQUEST_BUDGET: String(2 * adults + 4)});
    await check("ledger persists across a restart", async () => {
      const {status, data} = await compare(worker);
      assert.deepEqual([status, data], [429, {error: "request_budget_exhausted"}]);
    });
    await stop(worker);
    worker = await start({ASSET_ORIGIN: assetOrigin, TOMTOM_ENDPOINT: endpoint, TOMTOM_API_KEY: MOCK_KEY, TOMTOM_REQUEST_BUDGET: "2000"});
    await check("slow provider responses end at the comparison deadline", async () => {
      mock.delayMs = 16_000;
      const began = performance.now(), {status, data} = await compare(worker), seconds = (performance.now() - began) / 1000;
      mock.delayMs = 0;
      assert.deepEqual([status, data], [503, {error: "routing_unavailable"}]);
      assert.ok(seconds < 20, `took ${seconds.toFixed(1)} s`);
      return {seconds: +seconds.toFixed(1)};
    });
    await check("provider quota errors cool down, including across a restart", async () => {
      mock.status = 429;
      assert.deepEqual(await compare(worker), {status: 429, data: {error: "provider_limit_reached"}});
      mock.status = 200;
      const before = mock.starts.length;
      await stop(worker);
      worker = await start({ASSET_ORIGIN: assetOrigin, TOMTOM_ENDPOINT: endpoint, TOMTOM_API_KEY: MOCK_KEY, TOMTOM_REQUEST_BUDGET: "2000"});
      assert.deepEqual(await compare(worker), {status: 429, data: {error: "provider_limit_reached"}});
      assert.equal(mock.starts.length, before);
    });
    await check("an unconfigured gateway reports unavailable", async () => {
      await stop(worker);
      worker = await start({ASSET_ORIGIN: assetOrigin});
      assert.deepEqual(await (await fetch(worker.base + "/api/routes/status")).json(), {schema_version: 1, available: false});
      assert.deepEqual(await compare(worker), {status: 503, data: {error: "routing_not_configured"}});
    });
  }
} catch (error) {
  results.push({name: "harness", status: "failed", error: String(error.message ?? error).slice(0, 3000)});
} finally {
  if (worker) await stop(worker);
  assets.close();
  tomtom.close();
  // workerd releases its SQLite handles shortly after exit on Windows.
  await rm(persist, {recursive: true, force: true, maxRetries: 20, retryDelay: 250}).catch(() => {});
}

if (!args.has("--serve")) {
  const report = {checked_at: new Date().toISOString(), mode: args.has("--live") ? "live" : "mock",
    travel_generated_at: travel.generated_at, results};
  await mkdir(join(root, ".cache"), {recursive: true});
  await writeFile(join(root, ".cache", `gateway-${report.mode}-check.json`), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = results.every(r => r.status === "passed") ? 0 : 1;
}
