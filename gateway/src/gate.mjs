// State held by the gateway's single Durable Object: the usage ledger, the provider
// cooldown, and the one-comparison-at-a-time gate. No origins or keys are stored.
import {ENDPOINT, GatewayError, candidatesFrom, compareRoutes, responseBody, validateOrigin} from "./comparison.mjs";

const COOLDOWN_MS = 60_000;
const DAY_MS = 86_400_000;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export function budgetLimit(value) {
  if (value === undefined || value === null || value === "") return 20000;
  const text = String(value).trim(), limit = Number(text);
  if (!/^\d+$/.test(text) || limit < 1 || limit > 20000) throw new GatewayError("request_budget_unavailable");
  return limit;
}

// The endpoint override exists for local tests against a loopback mock; anything
// else could send the key elsewhere, so it disables routing instead.
export function endpointFrom(value) {
  if (!value || value === ENDPOINT) return ENDPOINT;
  try {
    const url = new URL(value);
    if (url.protocol === "http:" && LOOPBACK.has(url.hostname)) return value;
  } catch { /* Fall through to the configuration error. */ }
  throw new GatewayError("routing_not_configured");
}

export class RouteGateCore {
  constructor({sql, transaction, env, fetcher, clock = Date.now, sleep = ms => new Promise(r => setTimeout(r, ms))}) {
    Object.assign(this, {sql, transaction, env, fetcher, clock, sleep});
    this.busy = false;
  }

  key() { return String(this.env.TOMTOM_API_KEY ?? "").trim(); }

  // Conservative reservations over 32 UTC dates (31 complete days and today, covering
  // any monthly billing window). The whole comparison is reserved before any provider
  // call; failures and skipped calls are not refunded because a timeout may be billed.
  reserve(count, now) {
    const limit = budgetLimit(this.env.TOMTOM_REQUEST_BUDGET);
    try {
      this.transaction(() => {
        this.sql.exec("CREATE TABLE IF NOT EXISTS requests (day TEXT PRIMARY KEY, calls INTEGER NOT NULL CHECK(typeof(calls) = 'integer' AND calls >= 0))");
        const day = new Date(now).toISOString().slice(0, 10);
        const cutoff = new Date(now - 31 * DAY_MS).toISOString().slice(0, 10);
        const used = this.sql.exec("SELECT COALESCE(SUM(calls), 0) AS used FROM requests WHERE day >= ?", cutoff).toArray()[0].used;
        if (used + count > limit) throw new GatewayError("request_budget_exhausted");
        this.sql.exec("INSERT INTO requests VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls", day, count);
      });
    } catch (error) {
      throw error instanceof GatewayError ? error : new GatewayError("request_budget_unavailable");
    }
  }

  // The cooldown after an auth/quota error is persisted so eviction cannot clear it.
  blockedUntil() {
    this.sql.exec("CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value INTEGER NOT NULL)");
    return this.sql.exec("SELECT value FROM state WHERE name = 'blocked_until'").toArray()[0]?.value ?? 0;
  }

  block(until) {
    this.sql.exec("CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value INTEGER NOT NULL)");
    this.sql.exec("INSERT INTO state VALUES ('blocked_until', ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value", until);
  }

  async travel() {
    try {
      const url = new URL("travel.json", String(this.env.ASSET_ORIGIN).replace(/\/?$/, "/"));
      const response = await this.fetcher(url, {cache: "no-store", signal: AbortSignal.timeout(5000)});
      if (response.status !== 200) {
        try { await response.body?.cancel(); } catch { /* Connection cleanup only. */ }
        throw new Error("Travel context unavailable");
      }
      return await response.json();
    } catch { throw new GatewayError("routing_unavailable"); }
  }

  async compare(input) {
    try { return {ok: true, body: await this.run(input)}; }
    catch (error) { return {ok: false, code: error instanceof GatewayError ? error.message : "routing_unavailable"}; }
  }

  async run(input) {
    const origin = validateOrigin(input), key = this.key();
    if (!key) throw new GatewayError("routing_not_configured");
    const endpoint = endpointFrom(this.env.TOMTOM_ENDPOINT);
    if (this.busy) throw new GatewayError("rate_limited");
    this.busy = true;
    try {
      let blocked;
      try { blocked = this.clock() < this.blockedUntil(); } catch { throw new GatewayError("request_budget_unavailable"); }
      if (blocked) throw new GatewayError("provider_limit_reached");
      const candidates = candidatesFrom(await this.travel(), origin.age_group, this.clock());
      const now = this.clock();
      this.reserve(candidates.length, now);
      const departure = new Date(now).toISOString();
      const {routes, fatal} = await compareRoutes({origin, candidates, key, departure, endpoint,
        fetcher: this.fetcher, clock: this.clock, sleep: this.sleep});
      if (fatal.length) {
        // Stop this comparison and briefly block explicit retries; no partial claim.
        try { this.block(this.clock() + COOLDOWN_MS); } catch { /* The error below still stops this comparison. */ }
        throw new GatewayError(fatal.includes("routing_access_denied") ? "routing_access_denied" : "provider_limit_reached");
      }
      if (!routes.some(r => r.status === "ok")) throw new GatewayError("routing_unavailable");
      return responseBody(origin.age_group, departure, routes);
    } finally {
      this.busy = false;
    }
  }
}
