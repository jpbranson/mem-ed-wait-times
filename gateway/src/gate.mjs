// State held by the gateway's single Durable Object: the usage ledger, per-client and
// daily limits, the provider cooldown, and the one-comparison-at-a-time gate. No
// origins, keys or client addresses are stored.
import {ENDPOINT, GatewayError, candidatesFrom, compareRoutes, responseBody, validateOrigin} from "./comparison.mjs";

const COOLDOWN_MS = 60_000;
const CLIENT_WINDOW_MS = 600_000;
const DAY_MS = 86_400_000;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

// A malformed limit disables routing rather than silently lifting the limit.
function setting(value, fallback, max) {
  if (value === undefined || value === null || value === "") return fallback;
  const text = String(value).trim(), limit = Number(text);
  if (!/^\d+$/.test(text) || limit < 1 || limit > max) throw new GatewayError("request_budget_unavailable");
  return limit;
}

export const budgetLimit = value => setting(value, 20000, 20000);

// Provider requests per 32 UTC dates and per UTC date (all clients), and comparisons
// per client per 10 minutes and per UTC date. The daily cap keeps a client that
// rotates addresses from spending more than a day's share of the monthly budget.
export function limitsFrom(env) {
  return {monthly: budgetLimit(env.TOMTOM_REQUEST_BUDGET), daily: setting(env.TOMTOM_DAILY_BUDGET, 1000, 20000),
          burst: setting(env.CLIENT_BURST_LIMIT, 4, 1000), clientDaily: setting(env.CLIENT_DAILY_LIMIT, 20, 1000)};
}

const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
const utcDate = ms => new Date(ms).toISOString().slice(0, 10);

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
  // The client's comparison is recorded in the same transaction, so a rejected
  // comparison counts against nothing.
  reserve(count, now, client) {
    const limits = limitsFrom(this.env);
    try {
      this.transaction(() => {
        this.sql.exec("CREATE TABLE IF NOT EXISTS requests (day TEXT PRIMARY KEY, calls INTEGER NOT NULL CHECK(typeof(calls) = 'integer' AND calls >= 0))");
        this.sql.exec("CREATE TABLE IF NOT EXISTS clients (day TEXT NOT NULL, client TEXT NOT NULL, at INTEGER NOT NULL)");
        const day = utcDate(now), cutoff = utcDate(now - 31 * DAY_MS);
        const used = this.sql.exec("SELECT COALESCE(SUM(calls), 0) AS used FROM requests WHERE day >= ?", cutoff).toArray()[0].used;
        if (used + count > limits.monthly) throw new GatewayError("request_budget_exhausted");
        const today = this.sql.exec("SELECT COALESCE(SUM(calls), 0) AS calls FROM requests WHERE day = ?", day).toArray()[0].calls;
        if (today + count > limits.daily) throw new GatewayError("daily_budget_exhausted");
        // Client identifiers are salted per UTC date, so no row outlives its date.
        this.sql.exec("DELETE FROM clients WHERE day < ?", day);
        const mine = this.sql.exec("SELECT COUNT(*) AS today, COALESCE(SUM(at > ?), 0) AS recent FROM clients WHERE day = ? AND client = ?",
                                   now - CLIENT_WINDOW_MS, day, client).toArray()[0];
        if (mine.recent >= limits.burst || mine.today >= limits.clientDaily) throw new GatewayError("client_rate_limited");
        this.sql.exec("INSERT INTO requests VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls", day, count);
        this.sql.exec("INSERT INTO clients VALUES (?, ?, ?)", day, client, now);
      });
    } catch (error) {
      throw error instanceof GatewayError ? error : new GatewayError("request_budget_unavailable");
    }
  }

  // An HMAC of the client's network address under a random salt that is replaced each
  // UTC date. The address itself is never stored; the identifier stops matching the
  // same address at the next date, when its rows are deleted.
  async clientId(address, now) {
    const day = utcDate(now);
    try {
      let salt;
      this.transaction(() => {
        this.sql.exec("CREATE TABLE IF NOT EXISTS salts (day TEXT PRIMARY KEY, salt TEXT NOT NULL)");
        this.sql.exec("DELETE FROM salts WHERE day < ?", day);
        salt = this.sql.exec("SELECT salt FROM salts WHERE day = ?", day).toArray()[0]?.salt;
        if (!salt) {
          salt = hex(crypto.getRandomValues(new Uint8Array(32)));
          this.sql.exec("INSERT INTO salts VALUES (?, ?)", day, salt);
        }
      });
      const encode = text => new TextEncoder().encode(text);
      const key = await crypto.subtle.importKey("raw", encode(salt), {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
      return hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, encode(String(address)))).slice(0, 16));
    } catch { throw new GatewayError("request_budget_unavailable"); }
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

  // `address` is the client's network (see clientAddress in handler.mjs); callers
  // without one share a single limit.
  async compare(input, address = "unknown") {
    try { return {ok: true, body: await this.run(input, address)}; }
    catch (error) { return {ok: false, code: error instanceof GatewayError ? error.message : "routing_unavailable"}; }
  }

  async run(input, address) {
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
      this.reserve(candidates.length, now, await this.clientId(address, now));
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
