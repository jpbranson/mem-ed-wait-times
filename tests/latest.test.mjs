import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import {readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve, dirname, basename} from "node:path";
import {execFile} from "node:child_process";
import {promisify} from "node:util";
import {createFeed, facilityView, validateArtifact} from "../dashboard/latest.mjs";

const expected = [{slug: "memphis", display_name: "Memphis"}, {slug: "desoto", display_name: "DeSoto"}];
const base = Date.parse("2026-09-14T12:00:00Z");
function artifact(wait = 10, time = base) {
  const at = new Date(time).toISOString();
  return {schema_version: 1, metric: "CV_ED_Wait", generated_at: at,
    freshness: {stale_after_seconds: 1800, refresh_seconds: 60, request_timeout_seconds: 1, expected_collection_seconds: 900},
    facilities: expected.map(f => ({slug: f.slug, reporting_state: "reporting",
      last_success: {facility: f.slug, metric: "CV_ED_Wait", wait_minutes: wait, batch_id: at, observed_at: at, latency_ms: 10},
      last_attempt: {batch_id: at, attempted_at: at, state: "success", error_code: null}}))};
}

test("HTTP integration: new reading appears with unchanged site; failed refresh and aging cannot appear current", async t => {
  let latest = artifact(), fail = false, clock = base + 1000, pageRequests = 0;
  const page = '<div id="latest-waits"></div><script type="module" src="latest.mjs"></script>';
  const server = http.createServer((req, res) => {
    if (req.url === "/") { pageRequests++; res.end(page); return; }
    res.writeHead(fail ? 503 : 200, {"Content-Type": "application/json", "Cache-Control": "no-store"});
    res.end(JSON.stringify(latest));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const url = `http://127.0.0.1:${server.address().port}`;
  const initialPage = await (await fetch(url)).text();
  let shown;
  const feed = createFeed({url: url + "/data/latest.json", expected, now: () => clock, onChange: s => { shown = s; }});
  await feed.refresh();
  assert.match(shown.html, /10 min/);
  assert.match(shown.html, /Recently collected/);
  latest = artifact(0, base + 900000);
  clock += 900000;
  await feed.refresh();
  assert.match(shown.html, /0 min/);
  assert.doesNotMatch(shown.html, /10 min/);
  assert.equal(pageRequests, 1, "refresh fetches only data, not rebuilt HTML");
  fail = true;
  await feed.refresh();
  assert.match(shown.html, /Refresh failed/);
  assert.doesNotMatch(shown.html, /Recently collected/);
  clock += 1800000;
  feed.tick();
  assert.match(shown.html, /Stale/);
  assert.match(shown.html, /Refresh failed/);
  assert.doesNotMatch(shown.html, /Recently collected/);
  fail = false;
  await feed.refresh();
  assert.match(shown.html, /Stale/, "successful fetch of old artifact does not reset age");
  latest = artifact(25, clock);
  await feed.refresh();
  assert.match(shown.html, /25 min/);
  assert.match(shown.html, /Recently collected/);
  assert.equal(await (await fetch(url)).text(), initialPage);
});

test("missing, failed, negative/future time, threshold boundary, and zero remain distinct", () => {
  const a = artifact(0);
  assert.equal(facilityView(a.facilities[0], a, base + 1000).value, 0);
  assert.equal(facilityView(a.facilities[0], a, base + 1799000).current, true);
  assert.deepEqual(facilityView(a.facilities[0], a, base + 1800000).labels, ["Stale"]);
  assert.deepEqual(facilityView(a.facilities[0], a, base - 1).labels, ["Clock mismatch"]);
  a.facilities[0].last_attempt.state = "failed";
  assert.deepEqual(facilityView(a.facilities[0], a, base).labels, ["Collection failed"]);
  assert.deepEqual(facilityView(null, a, base).labels, ["Missing reading"]);
});

test("malformed, partial, duplicate and backward artifacts retain last valid data with refresh failure", async () => {
  let data = artifact();
  const feed = createFeed({expected, now: () => base + 1000,
    fetcher: async () => ({ok: true, json: async () => data})});
  await feed.refresh();
  for (const mutate of [a => { a.facilities.pop(); }, a => { a.facilities[1] = a.facilities[0]; },
    a => { a.facilities[0].last_success.wait_minutes = "20"; }, a => { a.metric = "OTHER"; },
    a => { a.facilities[0].last_success.observed_at = "bad"; }, a => { a.freshness.stale_after_seconds = 0; },
    a => { a.facilities[0].reporting_state = "missing"; }, a => { a.facilities[0].last_success.latency_ms = -1; },
    a => { a.generated_at = "2026-09-13T00:00:00Z"; }]) {
    data = artifact(99);
    mutate(data);
    await feed.refresh();
    assert.equal(feed.state().refreshFailed, true);
    assert.match(feed.state().html, /10 min/);
    assert.doesNotMatch(feed.state().html, /Recently collected/);
  }
});

test("request timeout marks refresh failed and keeps readings", async () => {
  const feed = createFeed({expected, now: () => base,
    fetcher: async (_, {signal}) => new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(Error("timeout"))))});
  // Default timeout is 10 seconds. No artifact has been loaded yet.
  await feed.refresh();
  assert.equal(feed.state().refreshFailed, true);
  assert.match(feed.state().html, /Missing reading/);
});

test("deployment sync protects independently published data", () => {
  const workflow = readFileSync(new URL("../.github/workflows/dashboard.yml", import.meta.url), "utf8");
  const sync = workflow.split("\n").find(line => line.includes("aws s3 sync"));
  assert.match(sync, /--delete\s+--exclude "data\/\*"/);
  assert.match(readFileSync(new URL("../dashboard/_quarto.yml", import.meta.url), "utf8"), /latest\.mjs/);
});

test("AWS CLI dry run excludes data artifacts from both upload and deletion", async t => {
  const run = promisify(execFile);
  try { await run("aws", ["--version"]); }
  catch (error) { if (error.code === "ENOENT") { t.skip("AWS CLI unavailable"); return; } throw error; }
  const directory = mkdtempSync(join(tmpdir(), "edwait-sync-"));
  t.after(() => {
    assert.equal(dirname(resolve(directory)), resolve(tmpdir()));
    assert.ok(basename(directory).startsWith("edwait-sync-"));
    rmSync(directory, {recursive: true, force: true});
  });
  mkdirSync(join(directory, "data"));
  writeFileSync(join(directory, "index.html"), "new site");
  writeFileSync(join(directory, "data", "local-only.json"), "must not upload");
  const contents = ["old.html", "data/latest.json"].map(key =>
    `<Contents><Key>${key}</Key><LastModified>2026-01-01T00:00:00Z</LastModified><ETag>&quot;abc&quot;</ETag><Size>10</Size><StorageClass>STANDARD</StorageClass></Contents>`).join("");
  const server = http.createServer((req, res) => {
    assert.equal(req.method, "GET", "dry run must never write");
    res.writeHead(200, {"Content-Type": "application/xml"});
    res.end(`<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>test</Name><Prefix></Prefix><KeyCount>2</KeyCount><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>${contents}</ListBucketResult>`);
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const result = await run("aws", ["s3", "sync", directory, "s3://test/", "--delete", "--exclude", "data/*", "--dryrun",
    "--endpoint-url", `http://127.0.0.1:${server.address().port}`, "--region", "us-east-1", "--no-sign-request", "--no-cli-pager"],
    {timeout: 20000, env: {...process.env, AWS_EC2_METADATA_DISABLED: "true"}});
  assert.match(result.stdout, /delete: s3:\/\/test\/old.html/);
  assert.match(result.stdout, /upload:.*index.html/);
  assert.doesNotMatch(result.stdout, /latest.json|local-only.json/);
});
