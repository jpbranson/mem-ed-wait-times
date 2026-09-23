// Read-only production smoke check using the same validators as the dashboard.
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {createHash} from 'node:crypto';
import {validateArtifact, facilityView} from '../dashboard/latest.mjs';
import {validateContext, contextAvailable} from '../dashboard/comparisons.mjs';
import {validateTravel, availableContext} from '../dashboard/travel.mjs';

const base = 'https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/';
const expected = JSON.parse(await readFile(new URL('../edwait/facilities.json', import.meta.url))).facilities;
const args = process.argv.slice(2);
const output = args.includes('--output') ? args[args.indexOf('--output') + 1] : null;
const after = args.includes('--expect-context-after') ? Date.parse(args[args.indexOf('--expect-context-after') + 1]) : null;
const expectedSite = args.includes('--expected-site') ? args[args.indexOf('--expected-site') + 1] : null;
if (after !== null) assert(Number.isFinite(after), 'Invalid expected context timestamp');
async function get(path, mime) {
  const response = await fetch(new URL(path, base), {cache:'no-store', signal:AbortSignal.timeout(30000)});
  assert.equal(response.status, 200, `${path}: HTTP ${response.status}`);
  assert.match(response.headers.get('content-type') ?? '', mime, `${path}: invalid Content-Type`);
  return {text:await response.text(), modified:response.headers.get('last-modified'), cache:response.headers.get('cache-control')};
}
const [html, latest, comparisons, travel] = await Promise.all([
  get('index.html', /text\/html/), get('data/latest.json', /application\/json/),
  get('comparisons.json', /application\/json/), get('travel.json', /application\/json/),
]);
const now = Date.now();
if (expectedSite) {
  for (const [path, value] of [['index.html', html], ['comparisons.json', comparisons], ['travel.json', travel]]) {
    assert.equal(value.text, await readFile(join(expectedSite, path), 'utf8'), `${path}: public bytes differ from this build`);
  }
}
const feed = validateArtifact(JSON.parse(latest.text), expected);
const context = validateContext(JSON.parse(comparisons.text), expected);
const routes = validateTravel(JSON.parse(travel.text), expected);
assert.match(latest.cache ?? '', /no-store/, 'Latest observations must not be cached');
assert(contextAvailable(context, now), 'Comparison context is expired or future-dated');
assert(availableContext(routes, now), 'Travel context is expired or future-dated');
if (after !== null) assert(Date.parse(context.generated_at) >= after, 'Context predates this build');
const views = feed.facilities.map(f => ({slug:f.slug, ...facilityView(f, feed, now)}));
assert(views.some(f => f.current), 'No current public observations');
assert.equal(routes.recommendations_enabled, false, 'M2 recommendation gate must remain off');
const report = {checked_at:new Date(now).toISOString(), status:'passed',
  matched_local_build: Boolean(expectedSite),
  html_sha256:createHash('sha256').update(html.text).digest('hex'), html_last_modified:html.modified,
  latest_generated_at:feed.generated_at, latest_age_seconds:(now-Date.parse(feed.generated_at))/1000,
  context_generated_at:context.generated_at, context_valid_until:context.valid_until,
  context_age_seconds:(now-Date.parse(context.generated_at))/1000,
  current_facilities:views.filter(f=>f.current).length, expected_facilities:expected.length,
  unavailable:views.filter(f=>!f.current).map(f=>({slug:f.slug,labels:f.labels})),
  recommendations_enabled:routes.recommendations_enabled};
if (output) { await mkdir(dirname(output), {recursive:true}); await writeFile(output, JSON.stringify(report,null,2)+'\n'); }
console.log(JSON.stringify(report,null,2));
