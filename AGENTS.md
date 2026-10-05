# Repository development instructions

## Living development plan

- Read [docs/development-plan.md](docs/development-plan.md) before making changes
  to product behavior, analytics, data contracts, or deployment.
- Keep that document current in the same change as relevant development. Update
  milestone status, remaining work, affected design decisions, and validation
  evidence. Follow its maintenance and completion rules.
- Distinguish planned, implemented, validated, and deployed behavior. Do not mark
  a milestone complete until its acceptance criteria are satisfied, and record
  deployment separately.
- Record significant scope or design changes in the plan's decision log. Preserve
  dated observations as historical evidence rather than presenting them as live facts.
- Update [docs/s3-buckets.md](docs/s3-buckets.md) and
  [docs/ed-wait.schema.json](docs/ed-wait.schema.json) when their documented
  storage or record contracts change.
- For routine work that does not affect the plan, leave it unchanged and state
  that briefly in the change summary. Documentation maintenance does not require
  a separate approval step.

## Knowledge bundle (Open Knowledge Format)

`docs/` is an [Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
bundle. Every document of project knowledge belongs there, and
`python scripts/okf.py check` (also run by `tests/test_knowledge.py`, which gates
the website build) must pass.

- Give every new `docs/*.md` YAML frontmatter with `type`, `title` (its H1),
  a one-sentence `description`, `tags`, `status` (`draft`, `stable` or
  `deprecated`) and `generated` (`by`, `at`). Reuse the existing types listed in
  [docs/index.md](docs/index.md) where one fits.
- When a document's content changes meaningfully, set `generated.at` to the UTC time
  of the change and `generated.by` to the actor: `claude-code/<model id>` for
  Claude Code, `human:<id>` for a person, `process:<id>` for a script. Scripts
  that regenerate a document must write through `write_concept` in
  `scripts/okf.py`, which keeps the frontmatter.
- Record what a report or research record derives from in `sources` (in-bundle
  evidence files or official pages, each with a `resource`). Add `verified` only
  when the named person or process has actually confirmed the content; never
  record a human review on someone's behalf.
- Mark a superseded document `status: deprecated` instead of deleting it.
- After adding a document or changing a `type`, `title`, `description` or
  `status`, run `python scripts/okf.py index` to regenerate `docs/index.md`.
  Add a dated entry to [docs/log.md](docs/log.md) for creations, deprecations,
  renames and structural changes.
- Never edit the frozen study protocols (`m2-benefit-protocol.md`,
  `m3-relationship-protocol.md`, `m5-study-protocol.md`). Their bytes are pinned
  by SHA-256 values recorded in study evidence, so they carry no frontmatter and
  are the bundle's only listed exceptions. The check fails if their hashes change.
