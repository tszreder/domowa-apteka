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

## Verify a database-engine behaviour difference before designing around it

- **Context**: `/10x-plan` output — the "Critical Implementation Detail" and
  risk framing in `context/changes/household-accounts-and-invites/plan.md:64-68`
  and `plan.md:110-116`.
- **Problem**: The plan stated that `unique=True` on a username column "is
  case-sensitive on Postgres and effectively case-insensitive on SQLite", and
  built a critical implementation detail on it: normalising only at signup would
  let `Alice@x.com` fail to log in against a stored `alice@x.com` in production
  while every test passed on CI's SQLite. Measured against Django's actual
  `auth_user` DDL (`varchar NOT NULL UNIQUE`, default BINARY collation), SQLite
  is case-sensitive here too — the lookup returns 0 rows and the mixed-case
  insert succeeds, same as Postgres. The `.lower()` guard and its test are real
  and CI does cover them; only the stated rationale was wrong. A future
  maintainer reading it could add a Postgres-only CI job to chase a
  non-problem.
- **Rule**: Before writing a dev-vs-production engine behaviour difference into
  a plan, verify it with the cheapest empirical check available — inspect the
  generated DDL, or run the query/insert against the dev engine. If no check
  fits the planning budget, mark the claim as unverified rather than stating it
  as fact.
- **Applies to**: all
