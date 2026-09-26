# M2 benefit-rule backtest — 2026-09-26 UTC

Result: **no candidate rule qualifies.** Under the [pre-registered protocol](m2-benefit-protocol.md)
(committed in `996a2f1` before scoring), no rule for calling an alternative's
drive-plus-published-wait estimate "meaningfully lower" reached 90% reliability on
discovery, so none was selected. Confirmation shows the same picture. Preferred-option
claims stay disabled, and the page's movement screen stays descriptive. Nothing public
changed. Aggregate output: [m2-benefit-results.json](m2-benefit-results.json).

## What was run

`scripts/m2_benefit.py` used 93,818 records from the frozen M5 snapshot (latest batch
2026-09-15 23:53 UTC; nothing from M5's final holdout or later), TomTom typical-speed
drive times from three public city centers to the 18 adult-eligible destinations
([profiles](m2-route-profiles-2026-09-26.json)), and M2's published 28-day movement
statistic as screen input. Closest hospitals: Crittenden from downtown Memphis,
Mississippi Baptist from downtown Jackson, Union County from downtown Tupelo.
Runtime 20 s.

An opportunity is an hourly moment, origin and alternative within 120 minutes'
drive where both hospitals had current readings, supported screens and readings at
arrival. A claim **holds** when the alternative still had the lower sum once each
hospital's published wait at its arrival replaced the wait at departure.

## Results

Discovery: 14,170 opportunities on 26 local days (8 August to 1 September).
Confirmation: 7,924 on 15 days (2–15 September). Precision is the share of claims
that held; intervals are day-block bootstrap 95%.

| Rule | Discovery claims | Discovery precision | Confirmation claims | Confirmation precision | Median / 10th pct `A` (disc.) |
| --- | --- | --- | --- | --- | --- |
| F0: any lower estimate | 2,223 | 0.790 (0.767–0.813) | 1,200 | 0.794 (0.738–0.851) | 19.6 / −23.4 min |
| F10 | 1,709 | 0.837 (0.808–0.866) | 928 | 0.838 (0.767–0.903) | 29.3 / −23.5 |
| F20 | 1,301 | 0.842 (0.807–0.874) | 737 | 0.840 (0.755–0.916) | 41.3 / −26.6 |
| F30 | 1,020 | 0.848 (0.805–0.887) | 588 | 0.849 (0.749–0.939) | 58.0 / −27.5 |
| F45 | 773 | 0.855 (0.796–0.912) | 438 | 0.854 (0.743–0.959) | 78.9 / −31.6 |
| F60 | 632 | 0.845 (0.776–0.912) | 353 | 0.844 (0.718–0.954) | 90.4 / −41.6 |
| S1: current screen | 636 | 0.852 (0.782–0.920) | 317 | 0.855 (0.741–0.956) | 84.3 / −43.0 |
| S½ | 982 | 0.875 (0.823–0.921) | 522 | 0.870 (0.773–0.961) | 56.4 / −22.1 |

Secondary outcomes (claims holding, discovery, confirmation similar):

| Rule | Readings 60 min after arrival | Alternative drive +20% |
| --- | --- | --- |
| F0 | 0.61 | 0.66 |
| F20 | 0.66 | 0.79 |
| F45 | 0.67 | 0.83 |
| S1 | 0.70 | 0.83 |
| S½ | 0.70 | 0.85 |

## Interpretation

- With fixed margins of 10–60 minutes, roughly one claim in six or seven reversed by
  arrival. Larger margins did not help: precision stayed near 0.84–0.86, and failures
  grew larger (10th percentile from −23 to −42 minutes). That pattern is consistent
  with large apparent advantages often coming from short-lived spikes, though this
  study did not test that directly.
- Scaling the margin to each hospital's own movement (S½) did best but still missed
  the 0.90 gate, and its lower bound in confirmation (0.77) is weak.
- Exploratory, not pre-registered: the Memphis origin drives the failures (precision
  about 0.72–0.81 under every rule; the closest hospital, Crittenden, sits among
  hospitals whose readings move by tens of minutes per hour). From Jackson and Tupelo
  the screen rules held 0.92–1.00, on fewer claims. A future study could pre-register
  per-area rules.
- If the published number is a trailing average, what a patient arriving now would
  experience resembles the reading about an hour later; judged that way, claims held
  only 60–70% of the time. Confirming the metric's definition matters as much as any
  threshold.
- Plausible drive-time error (+20%) lowered precision by about 3–13 points.

## What this means for M2

The drafted benefit rule is a negative one: **no margin tested can support a
"meaningfully lower" claim**, so the page should keep showing arithmetic differences
without a preferred option. A viable rule likely needs (1) confirmed metric semantics,
(2) better short-horizon expectations than the current reading (M5 found carry-forward
hard to beat), or (3) area-specific validation on longer history. Revisit with the
2026-10-15 checkpoint's fresh data, pre-registering any per-area rule first.

These results concern published readings from three public points with typical drive
times; they are not patient outcomes, clinical guidance or measured time savings.
