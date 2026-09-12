# Tasks: Phase 7 Zero-Spend Market Data

- [x] Confirm KIS authority, classification, scope, and Phase-7 scientific boundary.
- [x] Enforce zero automatic Databento spend and exact metadata quote-before-spend behavior.
- [x] Record the current Databento coverage gap and sub-dollar metadata quote without executing a billable request.
- [x] Add distinct Saxo LIVE endpoint/token handling and read-only entitlement inspection.
- [x] Verify in tests that LIVE readiness requires user/terms/account/NYMEX plus actual NG and MNG contract/chart access.
- [x] Add a separate ignored, hash-chained Saxo shadow ledger bound to an existing Phase-7 decision hash without mutating the canonical ledger.
- [x] Record execution promotion as paper -> Saxo SIM -> Saxo LIVE; LIVE order submission is final-stage only, while read-only LIVE verification remains non-promoting and may be performed earlier.
- [ ] Re-establish a fresh `SAXO_LIVE_ACCESS_TOKEN` and execute the sanitized LIVE readiness probe when needed for read-only account verification; this is no longer a landing blocker for this change and no secret is retained.
- [x] Run exact-tree change-workflow/governance checks and execute only missing verification/review evidence.
- [ ] Prepare and land the reviewable PR through KIS; reconcile documentation/work state and clean the worktree.
- [ ] Return the landed implementation identity to Phase 7; continue remaining serving/refreeze blockers without treating Saxo shadow data as scientific evidence.
