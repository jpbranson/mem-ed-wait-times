# M2 benefit-rule backtest protocol — 2026-09-26 UTC

Written and committed before any real-data scoring. It drafts the rule M2 needs
before release: when may the page say an alternative's drive-plus-published-wait
estimate is *meaningfully* lower than the closest option's? This study changes
nothing public. Recommendations stay disabled regardless of its result, because
metric semantics, entrances and live traffic remain unverified.

## Question

At a past moment, suppose the page had shown an alternative `a` with a lower
estimate than the closest hospital `c`. How often was `a` still lower once each
hospital's published wait at the moment of arrival replaced the wait at departure,
and which rule for claiming "meaningfully lower" keeps that reliable? The
outcome concerns published readings, never measured patient time.

## Inputs

- History: the frozen M5 snapshot `.cache/m5-history-20260923.json`, SHA-256
  `efda699fb411e72c49374024e847834bfd225f580789d6140034e235234588ed`, restricted to
  records whose `batch_id` is before `2026-09-16T00:00:00Z`. M5's final holdout
  (2026-09-16 to 09-23) and later data are neither scored nor inspected.
- Series: M1's latest reading per UTC 15-minute slot (`BaselineIndex`); negative
  readings excluded, zeros kept.
- Drive times: [m2-route-profiles-2026-09-26.json](m2-route-profiles-2026-09-26.json),
  TomTom typical-speed durations from three public city-center points (downtown
  Memphis, Jackson and Tupelo) to the 18 adult-eligible destinations. A departure at
  a local weekday 06:00–09:59 uses the 08:00 profile, weekday 15:00–18:59 the 17:00
  profile, and any other time the 03:00 profile.
- Destinations: today's 18 adult-eligible facilities, applied to every past date
  (assumes those emergency departments were operating throughout).

## Definitions

- Evaluation slots: UTC slots starting on the hour. Discovery: slot starts in
  `[2026-08-08T00:00Z, 2026-09-02T00:00Z)`. Confirmation:
  `[2026-09-02T00:00Z, 2026-09-16T00:00Z)`. Arrival readings may fall after a
  period's end but never at or after 2026-09-16T00:00Z.
- Departure `t` is the end of the evaluation slot. Each facility's current reading
  is its reading in that slot; both `c` and `a` must have one.
- `c` is the destination with the shortest drive from the origin for that
  departure's profile. Alternatives are all other destinations whose drive is at
  most 120 minutes (the longest movement horizon).
- Screen inputs: M2's published movement statistic, the 90th percentile absolute
  change at 15/30/60/120 minutes over the 28 complete previous local days
  (`edwait.travel.POLICY` with `edwait.stability`), at the smallest horizon at or
  above each facility's drive, supported (64 pairs, 8 days) for both facilities.
- Opportunity: an (origin, slot, alternative) with both current readings, both
  screens supported and both arrival readings present. Its apparent advantage is
  `D = (d_c + w_c(t)) − (d_a + w_a(t))`.
- Primary outcome: `A = (d_c + w_c(t + d_c)) − (d_a + w_a(t + d_a))`, where `w_i(x)`
  is the reading in the UTC slot containing `x`. A claim **holds** when `A > 0`.
- Secondary outcomes, descriptive only: `A60` uses readings 60 minutes after each
  arrival (in case the metric is a trailing average); `A_stress` lengthens the
  alternative's drive by 20% (profile peaks reached ×1.21), in both its drive term
  and its arrival time. Opportunities lacking a secondary reading are excluded from
  that outcome only.

## Candidate rules

A rule claims "meaningfully lower" when:

| Rule | Condition |
| --- | --- |
| F0 | `D > 0` (any lower estimate; reference) |
| F10, F20, F30, F45, F60 | `D ≥ 10, 20, 30, 45, 60` minutes |
| S1 | `D > 10 + p90_c + p90_a` (the page's current provisional screen) |
| S½ | `D > 10 + 0.5 × (p90_c + p90_a)` |

## Metrics

Per rule and period, overall and by origin: opportunities; claims; distinct local
days with a claim; claim rate; precision (share of claims that hold); a day-block
bootstrap 95% interval for precision (local days resampled with replacement, 2,000
draws, seed 20260926, draws without claims skipped); median and 10th percentile of
`A` among claims; and precision under `A60` and `A_stress`. Opportunities overlap
and cluster within episodes, so counts overstate independent evidence.

## Selection and confirmation

On discovery only, a rule is eligible with at least 50 claims on at least 5 local
days, precision at least 0.90 and a bootstrap lower bound at least 0.80. Select the
eligible rule with the most claims; ties prefer a fixed rule, then the larger
threshold. If none is eligible, no rule is selected.

Confirmation reports every rule but cannot change the selection. The selected rule
**confirms** with precision at least 0.90 on at least 20 claims over at least 3
days; fewer claims make the result inconclusive.

## Use of the result

A confirmed rule becomes M2's drafted benefit rule, recorded with its limits; the
page's provisional screen and disabled recommendations do not change in this study.
A failed or inconclusive rule is a valid result and keeps the current state.

## Limits

Three public origins only, not user locations; typical rather than observed drive
times; published readings rather than patient waits; the reading at arrival as a
proxy; today's eligibility applied to past dates; one late-summer period; hourly,
overlapping opportunities.
