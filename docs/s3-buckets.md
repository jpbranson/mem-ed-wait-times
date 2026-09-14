# S3 bucket reference

Last verified: 2026-09-11. This document combines the repository's producer and
consumer code with read-only inspection of the two live buckets. The record
schema was checked against three objects (1,960 records); historical data outside
those samples was not inspected.

## Overview

| Bucket | Purpose | Contents |
| --- | --- | --- |
| `s3://mem-ed-wait-times/` | Source data for ED wait-time analysis | Raw JSON Lines batches and daily gzip-compressed copies |
| `s3://mem-ed-wait-times-dashboard/` | Published dashboard | Rendered HTML and supporting website assets |

The machine-readable [ED wait record schema](ed-wait.schema.json) describes one
JSON object per line in both raw and compacted data. The dashboard bucket is
documented by its object layout below; its website files do not share a tabular
record schema.

## Data bucket: `mem-ed-wait-times`

### Object layout and encoding

```text
s3://mem-ed-wait-times/
  raw/ed_wait/dt=YYYY-MM-DD/YYYYMMDDTHHMMSSZ.jsonl
  compacted/ed_wait/dt=YYYY-MM-DD/data.jsonl.gz
```

| Property | Raw | Compacted |
| --- | --- | --- |
| Object granularity | One collection batch | One day's collected raw records |
| Serialization | UTF-8 JSON Lines; one object per line, with a trailing newline | The same JSON Lines, compressed with gzip |
| S3 `ContentType` | `application/x-ndjson` | `application/x-ndjson` |
| S3 `ContentEncoding` | Unset in inspected objects | `gzip` |
| Partition | `dt=YYYY-MM-DD`, from the batch's UTC start date | Same date as the source raw partition |

`dt` is part of the object key, not a field inside each record. The raw filename
uses the batch start time in UTC, at second precision. The `batch_id` field keeps
the full ISO timestamp. A facility observation can occur after the batch's start
date if collection crosses midnight.

### Record fields

All six fields are required and non-null in the current producer and all inspected
records. No additional fields are emitted by the current producer.

| Field | JSON type | Meaning |
| --- | --- | --- |
| `facility` | string | Facility slug sent as the upstream API's `fac` parameter, e.g. `arlington` |
| `metric` | string | Key returned by the upstream API. All inspected records use `CV_ED_Wait`; the producer accepts other keys too. |
| `wait_minutes` | integer | Upstream metric value converted using Python `int()`, stored in minutes |
| `observed_at` | string, date-time | UTC time recorded after the facility HTTP response succeeds, e.g. `2026-09-11T00:08:51.380937+00:00` |
| `batch_id` | string, date-time | UTC collection start timestamp shared by every record in a batch; this is not a UUID |
| `latency_ms` | integer | Python Requests `response.elapsed` converted to milliseconds and rounded; measures the facility HTTP request through response headers |

One record represents one facility and one API metric in one collection batch.
The expected logical key is `(batch_id, facility, metric)`; the storage and
compactor do not enforce uniqueness or deduplicate records.

The producer does not define valid ranges or sentinel meanings for
`wait_minutes`. The samples include zero, so retain it as a numeric value unless
upstream documentation establishes a different meaning. The precise clinical
definition of `CV_ED_Wait` is not defined in this repository.

Actual record from the first inspected raw object:

```json
{
  "facility": "arlington",
  "metric": "CV_ED_Wait",
  "wait_minutes": 34,
  "observed_at": "2026-09-11T00:08:51.380937+00:00",
  "batch_id": "2026-09-11T00:08:50.867368+00:00",
  "latency_ms": 512
}
```

### Facilities

The producer lists these 20 facility slugs, all of which appeared in the samples:

```text
arlington
childrens
collierville
huntingdon
memphis
tipton
union-city
crittenden
nea
anderson
baptist-medical-center-attala
booneville
calhoun
desoto
golden-triangle
baptist-medical-center-leake
north-mississippi
union-county
baptist-medical-center-yazoo
baptist-medical-center
```

These are current values, not a closed schema enumeration. A failed facility
request is logged and skipped, so a batch need not include every facility. The
producer emits one record for each returned metric, so batch size also depends
on the upstream response.

### Reading and combining records

1. Select each desired UTC date partition.
2. If that date has compacted data, read it. Otherwise, read its raw batches.
3. Decompress `.gz` objects before decoding UTF-8 and parsing individual nonblank
   lines as JSON. Account for any decompression already performed by your client.
4. Combine the selected dates. Parse `observed_at` and `batch_id` as timestamps
   with a timezone. Group by both `facility` and `metric` for metric-specific
   analysis, and sort by `observed_at` when chronological order matters.

Do not concatenate raw and compacted data for the same date: compacted objects
contain copies of the raw records. The compactor concatenates raw files in object
key order; it does not aggregate, validate, or deduplicate their records. It
overwrites the destination object on rerun and leaves the source raw objects in
place. A compacted object reflects the raw files available at compaction time;
its existence alone does not establish that a day is complete.

The compactor defaults to the previous UTC day and also accepts an explicit
`date` value in `YYYY-MM-DD` form. The collection and compaction schedules are not
defined in this repository.

## Website bucket: `mem-ed-wait-times-dashboard`

Observed live layout:

```text
s3://mem-ed-wait-times-dashboard/
  index.html
  site_libs/
    bootstrap/
    clipboard/
    quarto-dashboard/
    quarto-html/
    quarto-nav/
    quarto-search/
```

`index.html` has S3 `ContentType: text/html`. The `site_libs/` prefixes hold
supporting Quarto website assets; individual asset filenames can change with
the renderer version. No separate record dataset was observed at the bucket
root. The HTML is a generated presentation of the data; use the data bucket for
record-level analysis.

The repository's deployment workflow renders `dashboard/` with Quarto and syncs
`dashboard/_site/` to this bucket with `--delete`. It is configured to run hourly
at minute zero and supports manual execution. Its AWS region setting is
`us-east-1`. Live bucket region, hosting configuration, and access policies were
not inspected.

The dashboard source reads the data bucket, prefers compacted data for each date,
falls back to raw data, and defaults to seven dates ending on the rendering
machine's `date.today()`. It converts observation times to `America/Chicago` for
display. Its charts use `wait_minutes` and `latency_ms` by facility. The website
object listing and HTML content type were verified; the deployed page's contents
were not compared with the local source.

## Sources and verification

Repository sources:

- [Collector and raw record writer](../mem-ed-lambda.py): `fetch_facility`,
  `build_key`, `collect`, and `write_s3`.
- [Daily compactor](../lambda_function.py): `compact` and `lambda_handler`.
- [Dashboard data reader and charts](../dashboard/index.qmd).
- [Quarto output configuration](../dashboard/_quarto.yml).
- [Dashboard render and deployment workflow](../.github/workflows/dashboard.yml).

Both Lambda scripts take their bucket name from the `BUCKET` environment
variable. The dashboard reader names `mem-ed-wait-times` explicitly, and the
deployment workflow names `mem-ed-wait-times-dashboard` explicitly. Deployed
Lambda environment variables were not inspected.

Live record samples, all within `s3://mem-ed-wait-times/`:

| Object key | Parsed records |
| --- | ---: |
| `raw/ed_wait/dt=2026-09-11/20260911T000850Z.jsonl` | 20 |
| `raw/ed_wait/dt=2026-09-11/20260911T193850Z.jsonl` | 20 |
| `compacted/ed_wait/dt=2026-09-10/data.jsonl.gz` | 1,920 |

Every sampled record had exactly the six documented fields with the documented
JSON types, with no null or missing fields. The raw and compacted content types
and compression metadata matched the code. The bucket roots, recent date
prefixes, website asset prefixes, and dashboard HTML metadata were also checked.
This is a sampled verification, not a full historical inventory or a guarantee
of future upstream values.

To refresh this reference, review the producer and consumer files above, list
recent raw and compacted objects with `aws s3api list-objects-v2`, download a few
with `aws s3api get-object`, and compare parsed records with
[ed-wait.schema.json](ed-wait.schema.json). Apply the schema to each JSON line
after decompression, enabling date-time format validation in your validator.
Update this verification date and the sample keys when doing so.
