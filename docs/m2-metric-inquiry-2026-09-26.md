# M2 metric inquiry draft — 2026-09-26 UTC

Status: **draft, not sent.** Sending it is the user's decision; nobody has contacted
Baptist about the metric. Record any reply here with its date and sender, then update
the development plan's open-decisions table. Until an answer arrives, `CV_ED_Wait`
semantics stay unconfirmed and continue to block preferred-option recommendations.

## What the project can already see

- Endpoint: `https://sites.bmhcc.org/api/waittimes/waittimes.php?fac=<slug>`, one
  request per facility. A response is a one-key object with a string integer, for
  example `{"CV_ED_Wait" : "91"}` (Memphis, 2026-09-26 00:09 UTC).
- The response carries no timestamp, `Last-Modified`, or caching headers. It is
  served dynamically (`cf-cache-status: DYNAMIC`), so update timing cannot be
  inferred from the response itself.
- Zero is common at some sites: about 19% of Arlington and 33% of Yazoo readings in
  the 2026-07-29 to 2026-09-13 assessment. Its meaning is unknown.
- The only definition found is a [2017 Baptist Tipton article](https://www.baptistonline.org/news/baptist-tipton-makes-er-wait-times-visible-to-patients/):
  a previous-hour average from arrival to first seeing a doctor or nurse
  practitioner, updated every five minutes. It may not describe the current feed
  or every facility.

## Suggested recipient

Baptist Memorial Health Care's marketing or digital team (owners of the wait
widget on baptistonline.org location pages), via the site's contact form or media
relations. The user may know a better contact.

## Draft message

> Subject: Question about the ER wait times published on baptistonline.org
>
> Hello,
>
> I run a small public, noncommercial website that charts the approximate ER wait
> times Baptist publishes for its hospitals, so people can see how today's reading
> compares with that hospital's usual range. I want to describe the number
> accurately and would be grateful for answers to a few questions:
>
> 1. What does the published wait measure — for example, from arrival or
>    registration to being seen by a physician or advanced practice provider?
> 2. Which patients are included, and over what window is it averaged (for
>    example, patients seen in the previous hour)?
> 3. How often is the value updated?
> 4. What does a wait of 0 mean — no recent patients, no wait, or data
>    unavailable? Are any other values used as placeholders?
> 5. Is the definition the same for every Baptist emergency department, including
>    Children's, Arlington, and the critical access hospitals?
> 6. Is it acceptable to display these published values with attribution, and is
>    there a preferred way to access them?
>
> The site labels every value as Baptist's approximate published wait, notes that
> serious conditions are treated first through triage, and directs emergencies to
> 911. Thank you for your help.

## After a reply

Record the answer, date and responder above. Then update the development plan's
metric row, the `metric` description in [the raw schema](ed-wait.schema.json) if
the definition is confirmed, and M2's recommendation blockers. A partial answer
should be recorded as partial.
