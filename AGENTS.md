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
