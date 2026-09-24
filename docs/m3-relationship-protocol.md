# M3 relationship study protocol — 2026-09-24 UTC

Status: fixed before computing any pair statistic. This offline study describes
associations among published `CV_ED_Wait` readings. It cannot show patient
movement, diversion, capacity or causal spillover, and it publishes no artifact.

## Inputs and series

- Reuse M5's frozen snapshot (`2026-07-29T00:00:00Z` to `2026-09-23T00:00:00Z`,
  SHA-256 `efda699fb411e72c49374024e847834bfd225f580789d6140034e235234588ed`).
  Refuse any other input. Slots follow M5's half-open 15-minute UTC grid and
  tie rule; negative readings are excluded, zeros retained, nothing is filled.
- Calendar adjustment: each slot's deviation is its reading minus M1's past-only
  usual median (28 local days before the reading's America/Chicago day, weekday/
  weekend hour ±1, M1's support and fallbacks). Unsupported slots are missing.
  This is the same quantity the dashboard heatmap colors.
- Hourly UTC bins take the median deviation of their supported slots and need at
  least two. Chicago offsets are whole hours, so bins never straddle local days.
- Changes are differences between consecutive hourly bins; a gap breaks a change.

## Periods

| Period | Bins, inclusive start/exclusive end | Use |
| --- | --- | --- |
| Discovery | 2026-08-12 through 2026-09-02 UTC | Screen all pairs and lags |
| Confirmation | 2026-09-02 through 2026-09-16 UTC | Re-test only discovery candidates |
| Reserved | 2026-09-16 through 2026-09-23 UTC | M5's final holdout; not read by M3 |

Discovery starts after two weeks of history so most M1 references are supported.
No threshold, lag range or grouping may change after confirmation is scored.

## Neighbor groups

Fixed from registry campus points before any wait statistic was computed: a
neighbor pair has campus centers within 50 km great-circle distance (21 pairs,
mostly Memphis metro). Groups are connected components of neighbor pairs.
Straight-line distance is not travel time, and campus centers are not reviewed
ER entrances. Children's serves children only, so its pairs compare different
service populations. All 190 pairs are tested; distance is reported, not used to
select tests. Summaries compare neighbor pairs with pairs 50–150 km and over
150 km apart.

## Statistics

For every pair A/B with at least 168 common bins over at least seven UTC days
(a day counts with 12 or more common bins):

1. **Same-time co-deviation:** Spearman correlation of hourly deviations.
2. **Same-time changes:** Spearman correlation of hourly changes.
3. **Lagged changes:** Spearman correlation of A's change at hour *t* with B's
   change at *t + k*, for k = 1, 2, 3 hours, in both directions.

Serial dependence: two-sided p-values use Fisher's z with an effective sample
size `n(1 − ρA·ρB)/(1 + ρA·ρB)` from each ranked series' lag-1 autocorrelation over
the common bins (capped at n; Bretherton et al., 1999). Multiple testing:
Benjamini–Hochberg at q = 0.10 separately within each family (190, 190 and
1,140 tests).

Robustness checks, each required to keep the sign with nominal p < 0.05:

- **System-wide swing:** partial Spearman correlation controlling for the median of
  the other facilities' values in the same bin (the follower's bin for lags),
  with at least five of them reporting.
- **Residual time of day:** correlation after removing each facility's mean by
  Chicago hour of day within the period.

A lagged candidate must also exceed the reverse direction at the same lag.

## Candidates, confirmation and labels

A discovery **candidate** passes BH, both robustness checks, and |ρ| ≥ 0.20.
Confirmation re-tests only candidates, with BH at q = 0.10 across them, the same
sign, |ρ| ≥ 0.10, both robustness checks and (for lags) direction dominance.

- **Confirmed** pairs may be described as "often rise and fall together" or, for
  lags, "changes historically preceded", always as associations of published
  readings. Three weeks plus two later weeks is still short; confirmation is not
  proof of a stable relationship.
- Pairs involving a facility with more than 10% zero readings in a period are
  labeled **exploratory** whatever their scores, because zero's meaning is unknown.
- Everything else is **not supported**, including candidates that fail confirmation.

For display only, candidates receive 95% percentile intervals from 1,000 paired
UTC-day block bootstrap resamples (seed 20260924). Confirmed pairs list up to five
episodes: runs of consecutive bins in which both facilities are at least 10
minutes above usual (M1's meaningful distance), for inspection in the heatmap.

## Deliverables and boundaries

Check in this protocol, code, tests, aggregate results and a dated report;
retain origin-level output in ignored `build/m3-study`. No `relationships.json`,
schema, S3 object or dashboard change is introduced. The held-out predictive
check (whether neighbor readings improve forecasts beyond each facility's own
history) remains a separate step sharing M5's harness and must not read M5's
final holdout before M5 freezes its choices.

## Execution note — 2026-09-24 UTC

Recorded after the first run; no rule, threshold or period was changed. The
rationale above that two weeks of history make most M1 references supported was
wrong: M1 requires 75% slot coverage across all 28 lookback days, so the first
supported discovery bin is 2026-08-19T05:00Z (Chicago midnight). Discovery
therefore contributed 14 supported days (about 331 bins per facility), not 21.

Reference: Bretherton, C. S., et al. (1999), "The effective number of spatial
degrees of freedom of a time-varying field", *Journal of Climate* 12, 1990–2009.
