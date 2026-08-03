# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Verify a platform limitation before registering it as a risk

- **Context**: `/10x-infra-research` output — the risk register and platform
  comparison in `context/foundation/infrastructure.md`.
- **Problem**: `infrastructure.md` recorded "no easy in-place region migration"
  as a high-certainty risk, and its pre-mortem narrative claimed that moving
  regions meant re-provisioning the database and re-pointing DNS during a
  maintenance window. On 2026-08-02 the migration took two `railway scale`
  commands, in place, with no re-provisioning and no DNS change. Downstream
  skills read foundation contracts as ground truth, so an untested negative
  capability claim silently rules out cheap options.
- **Rule**: Before writing a capability limitation into a foundation contract,
  attempt the cheapest empirical check available (CLI `--help`, API schema, docs
  published by the vendor). If no check is possible within the research budget,
  record the claim as unverified rather than omitting the caveat.
- **Applies to**: all
