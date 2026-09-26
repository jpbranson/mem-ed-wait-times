# Routing gateway (Cloudflare Workers)

Public routing gateway for M2's Drive + wait comparison: a Worker that passes the
static dashboard through from S3 and serves `/api/routes` at the same origin, with
one SQLite Durable Object holding the TomTom usage ledger, per-client and daily
rate limits, cooldown and one-comparison gate. **Validated locally and deployed on 2026-09-26 at an address not yet linked publicly.**

- [`src/comparison.mjs`](src/comparison.mjs): validation, destinations from the
  published `travel.json`, TomTom requests and route parsing (port of `edwait/routing.py`).
- [`src/gate.mjs`](src/gate.mjs): ledger, rate limits, cooldown and serialization.
- [`src/handler.mjs`](src/handler.mjs): HTTP boundary, client network and static pass-through.
- [`src/index.mjs`](src/index.mjs): Worker entry and Durable Object class.
- [`scripts/local-check.mjs`](scripts/local-check.mjs): end-to-end check in `wrangler dev`.

Unit tests live in [`../tests/gateway.test.mjs`](../tests/gateway.test.mjs) and run
with the site's Node suite. Design, local commands, validation evidence, privacy and
deployment steps: [M2 operations](../docs/m2-operations.md#cloudflare-gateway).
