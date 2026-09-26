// Cloudflare Worker entry: static dashboard pass-through plus the routing API.
import {DurableObject} from "cloudflare:workers";
import {RouteGateCore} from "./gate.mjs";
import {handle} from "./handler.mjs";

// Wrapped so the runtime's fetch is never invoked with a foreign `this`.
const fetcher = (url, init) => fetch(url, init);

export class RouteGate extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.core = new RouteGateCore({sql: ctx.storage.sql, transaction: fn => ctx.storage.transactionSync(fn), env, fetcher});
  }

  compare(input) {
    return this.core.compare(input);
  }
}

export default {
  fetch(request, env) {
    // One named object serializes comparisons and holds the only usage ledger, so
    // redeploys and concurrent visitors share a single budget.
    const gate = env.ROUTE_GATE.get(env.ROUTE_GATE.idFromName("route-gate"));
    return handle(request, env, {gate, fetcher});
  }
};
