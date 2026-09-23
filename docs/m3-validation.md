# M3 validation — relationships explorer

M3 is **in progress**. The first deliverable, a facility-by-time heatmap of
difference from usual with linked facility histories, is implemented. Neighbor
groups, lag analysis, held-out predictive checks, geographic placement and replay
remain planned. Nothing in this view claims patient movement or causal spillover.

## Heatmap — 2026-09-23 UTC

Implementation: [renderer and binning](../dashboard/heatmap.mjs), page section in
[index.qmd](../dashboard/index.qmd), wiring in [app.mjs](../dashboard/app.mjs),
styles in [latest.css](../dashboard/latest.css), tests in
[heatmap.test.mjs](../tests/heatmap.test.mjs).

Behavior:

- Rows are the 20 registry hospitals in registry order, labelled with the shared
  short names also used by the overview legend (`edwait.data.short_name`).
- Columns are clock-aligned UTC bins ending at the prepared history's cutoff:
  hourly for the seven-day view (168 columns) and 15-minute for the 24-hour view
  (96 columns). The shared time control drives both the overview and heatmap.
  Chicago offsets are whole hours, so bins align to local hours across DST.
- Each cell is the **median** of M1's per-reading difference from the past-only
  usual median (`comparisons.json` history column 5). No new artifact, schema or
  storage contract is introduced; the view reuses the build-time history.
- Seven discrete diverging steps: within ±10 minutes (M1's meaningful distance)
  is neutral gray; 10–20, 20–40 and 40+ minutes step toward blue (below usual)
  or red (above usual). Lightness rises symmetrically with magnitude on the dark
  surface (OKLab L 0.48/0.62/0.76 below, 0.50/0.62/0.79 above, 0.39 neutral).
- Periods without readings are blank. Periods with readings but no supported
  usual range are hatched, so missing and unsupported data stay distinct.
- Each cell has a tooltip with the full hospital name, Chicago time span, median
  difference and reading count. A disclosure holds a per-hospital summary table
  (periods observed, supported, 10+ above, 10+ below, largest above) and a
  limits note that aligned colors do not show patients moving between hospitals.
- Selecting a row by click, tap, Enter or Space focuses that hospital in the
  individual chart above and scrolls to it; the selected row label is highlighted.
- Axis labels fall on Chicago midnights (seven days) or 6-hour marks (24 hours),
  thinned to fit the width. The chart keeps a 560 px drawing minimum and scrolls
  horizontally inside its own region on narrow screens, like the focus chart.

Validation:

- Five JavaScript tests cover band thresholds, bin alignment and counts, medians
  over supported readings, unsupported and empty periods, ignored out-of-window
  readings, hospitals without history, HTML escaping, focus state, summary table,
  and midnight/6-hour labels across the 2026-11-01 DST change.
- A Python test now checks every browser module imported by `app.mjs` and
  `overview.mjs` is in Quarto's resource list; the first render omitted
  `heatmap.mjs` until it was added.
- Rendered with live read-only S3 history (20 facilities, 13,439 seven-day points,
  generated 07:05:46 UTC) and reviewed in Chrome at desktop width: 3,340 hourly
  cells over 20 rows; 1,900 cells in the 24-hour view; row click and Enter changed
  the focus selection; minimum text size 16 px; no console errors.
- 390 and 320 px same-origin frames: no page-width overflow, legend wraps, chart
  scrolls inside its region, 16 px minimum text, and no clipped row labels after
  widening the narrow label column to 168 px.

Limits: this is a descriptive exploration of published readings relative to each
hospital's own past. Shared weekday/hour effects are partly removed by the M1
reference but not modeled; collection gaps, reporting changes and zero readings
of unconfirmed meaning can align across rows. The M3 acceptance criteria
(episode inspection, calendar/serial-dependence checks, stability in later periods)
are not yet met.
