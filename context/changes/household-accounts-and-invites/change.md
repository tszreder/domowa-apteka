---
change_id: household-accounts-and-invites
title: Household accounts and invites
status: impl_reviewed
created: 2026-08-05
updated: 2026-08-07
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

Phase 5's manual item 5.9 ("End-to-end run on the live URL") was confirmed against the
deployed Railway URL after PR #11 merged: `/health/` returns 200, `/list/` correctly
redirects an anonymous request (302), and the end-to-end account/household flow was
confirmed working on the live site. Same pattern as Phase 4's separate
"confirm Phase 4 production deploy" commit (ed25402).
