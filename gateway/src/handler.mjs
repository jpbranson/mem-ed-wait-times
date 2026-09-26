// HTTP boundary of the gateway: the same /api/routes contract as edwait/serve.py, plus a
// pass-through of the static dashboard so the page and its API share one origin.

const API_HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-store",
                     "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"};
const TOO_MANY = new Set(["rate_limited", "client_rate_limited", "provider_limit_reached", "request_budget_exhausted",
                          "daily_budget_exhausted"]);
const UNAVAILABLE = new Set(["routing_unavailable", "routing_not_configured", "routing_access_denied", "request_budget_unavailable"]);
// Conditional and range headers only: no cookies or credentials reach the asset bucket.
const FORWARDED = ["If-None-Match", "If-Modified-Since", "Range"];
const DROPPED = /^(x-amz-|server$|set-cookie$)/i;

// The client's network for per-client limits: an IPv4 address, or an IPv6 /64 (one
// subscriber usually holds a whole /64 and can rotate addresses within it). Cloudflare
// sets CF-Connecting-IP; anything unparseable shares one "unknown" limit.
export function clientAddress(value) {
  const text = String(value ?? "").trim().toLowerCase();
  const octets = text.split(".");
  if (octets.length === 4 && octets.every(o => /^\d{1,3}$/.test(o) && Number(o) <= 255)) return octets.map(Number).join(".");
  const halves = text.split("::");
  if (!/^[0-9a-f:]+$/.test(text) || halves.length > 2) return "unknown";
  const [left, right] = halves.map(h => h ? h.split(":") : []);
  const zeros = 8 - left.length - (right?.length ?? 0);
  if (right ? zeros < 1 : zeros !== 0) return "unknown";
  const groups = [...left, ...Array(right ? zeros : 0).fill("0"), ...(right ?? [])];
  if (!groups.every(g => /^[0-9a-f]{1,4}$/.test(g))) return "unknown";
  return groups.slice(0, 4).map(g => g.padStart(4, "0")).join(":") + "::/64";
}

export const statusFor = code => TOO_MANY.has(code) ? 429 : UNAVAILABLE.has(code) ? 503 : 422;
const api = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {status, headers: {...API_HEADERS, ...headers}});

// Nothing here logs; request bodies and coordinates exist only for the life of the request.
export async function handle(request, env, {gate, fetcher}) {
  const url = new URL(request.url);
  if (url.pathname === "/api/routes/status") {
    if (request.method !== "GET") return api({error: "method_not_allowed"}, 405, {Allow: "GET"});
    // Lets the page enable Compare only where this gateway is configured.
    return api({schema_version: 1, available: Boolean(String(env.TOMTOM_API_KEY ?? "").trim())});
  }
  if (url.pathname === "/api/routes") {
    if (request.method !== "POST") return api({error: "method_not_allowed"}, 405, {Allow: "POST"});
    if (request.headers.get("Origin") !== url.origin) return api({error: "origin_rejected"}, 403);
    let input;
    try {
      const size = Number(request.headers.get("Content-Length"));
      if (!(size > 0 && size <= 512) || (request.headers.get("Content-Type") ?? "").split(";")[0].trim() !== "application/json")
        throw new Error("Invalid request");
      const text = await request.text();
      if (new TextEncoder().encode(text).length > 512) throw new Error("Invalid request");
      input = JSON.parse(text);
    } catch { return api({error: "invalid_request"}, 400); }
    let result;
    try { result = await gate.compare(input, clientAddress(request.headers.get("CF-Connecting-IP"))); } catch { result = {ok: false, code: "routing_unavailable"}; }
    return result.ok ? api(result.body) : api({error: result.code}, statusFor(result.code));
  }
  if (url.pathname.startsWith("/api/")) return api({error: "not_found"}, 404);
  return assets(request, env, fetcher, url);
}

async function assets(request, env, fetcher, url) {
  if (request.method !== "GET" && request.method !== "HEAD")
    return new Response("Method not allowed", {status: 405, headers: {Allow: "GET, HEAD"}});
  const path = url.pathname.endsWith("/") ? url.pathname + "index.html" : url.pathname;
  const headers = new Headers();
  for (const name of FORWARDED) if (request.headers.has(name)) headers.set(name, request.headers.get(name));
  try {
    // Query strings are dropped: the page never uses them and S3 treats some as subresources.
    // Bypass Cloudflare's cache: it would otherwise keep .css/.js from an earlier site build
    // (seen 2026-09-26). Cache headers pass through, including no-store on data/latest.json.
    const upstream = await fetcher(new URL(path, env.ASSET_ORIGIN),
                                   {method: request.method, headers, redirect: "manual", cache: "no-store"});
    const out = new Headers();
    for (const [name, value] of upstream.headers) if (!DROPPED.test(name)) out.set(name, value);
    // The bucket sets no cache policy on site files; make browsers revalidate (cheap 304s
    // by ETag) so each build is seen at once instead of after a heuristic delay.
    if (!out.has("Cache-Control")) out.set("Cache-Control", "no-cache");
    out.set("X-Content-Type-Options", "nosniff");
    return new Response(upstream.body, {status: upstream.status, headers: out});
  } catch {
    return new Response("Dashboard temporarily unavailable", {status: 502, headers: {"Cache-Control": "no-store"}});
  }
}
