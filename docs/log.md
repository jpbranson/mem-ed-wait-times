# Knowledge bundle update log

Dates are UTC. Entries before 2026-10-05 were reconstructed from git: each one gives the
date a document was first committed, which can be later than the work it describes.
Record creations, deprecations, renames and structural changes here; routine edits are
tracked by each document's `generated` frontmatter and in git.

## 2026-10-05
* **Initialization**: Adopted Open Knowledge Format v0.2 for `docs/`. Added frontmatter
  (`type`, `title`, `description`, `tags`, `status`, `generated`, and `sources` for
  evidence-based reports and research) to all 21 concept documents, a generated
  [index](index.md), this log, and `scripts/okf.py` with a unit test. `generated` comes
  from each document's last content commit. The three frozen study protocols stay
  byte-identical without frontmatter, and the check verifies their recorded SHA-256 values.

## 2026-09-27
* **Creation**: [Regional ER publication collector](regional-collector.md).
* **Creation**: [Memphis-area ERs without published wait information](map-facilities-2026-09-27.md).

## 2026-09-26
* **Creation**: [M2 metric inquiry draft](m2-metric-inquiry-2026-09-26.md).
* **Creation**: [M2 benefit-rule backtest](m2-benefit-validation.md).
* **Creation**: [M2 benefit-rule backtest protocol](m2-benefit-protocol.md), committed before scoring.
* **Creation**: [Flight log: next-steps run](flight-log-2026-09-26.md).

## 2026-09-24
* **Creation**: [M5 candidate study (v2)](m5-candidates-validation.md); the
  [M5 protocol](m5-study-protocol.md) gained its amendment before calibration scoring.
* **Creation**: [M4 validation](m4-validation.md).
* **Creation**: [M3 relationship study protocol](m3-relationship-protocol.md), committed before scoring.

## 2026-09-23
* **Creation**: [Production follow-up](production-followup-2026-09-23.md).
* **Creation**: [M5 benchmark checkpoint](m5-validation.md), [M5 ARIMA development pilot](m5-arima-validation.md)
  and the [M5 offline study protocol](m5-study-protocol.md).
* **Creation**: [M3 validation](m3-validation.md).
* **Creation**: [M2 readiness follow-up](m2-readiness-2026-09-23.md) and
  [M2 destination evidence](m2-destinations-2026-09-23.md).
* **Creation**: First commit of the [development plan](development-plan.md),
  [AWS deployment record](aws-deployment-2026-09-22.md), [M0 operations](m0-operations.md),
  [M1 operations](m1-operations.md), [M1 validation](m1-validation.md),
  [M2 operations](m2-operations.md) and [M2 validation](m2-validation.md); several describe
  work from 2026-09-14.

## 2026-09-14
* **Creation**: [S3 bucket reference](s3-buckets.md).
