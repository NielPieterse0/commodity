# Tasks: V2 Parallel Optimizer Hardening

- [x] Confirm live KIS authority, classification, scope, and required artifacts.
- [x] Map Programme #393 and #425 execution-integrity requirements into a bounded new module without modifying #425 scored code/evidence.
- [x] Implement deterministic balanced shards, frozen identity binding, exclusive leases, liveness/stale detection, host-bounded workers, atomic shard results, deterministic reduce, resume, and concurrent orchestration.
- [x] Complete identity-scoped/path-safe shard IDs plus strict serialized-ID reconstruction and malformed-manifest normalization.
- [x] Add repository operating rules for Work Management/issue-comment coordination, isolated concurrent KIS changes/worktrees, fenced reassignment, and single-agent fallback.
- [x] Add focused tests; 42 focused tests pass and focused Ruff is clean.
- [x] Run `pwsh -File scripts/change-workflow.ps1 check`.
- [x] Use live KIS review evidence: exact staged source code-quality and exact staged test-quality reviews both closed with no blocking findings after fixes.
- [ ] Prepare the reviewable PR from valid PromotionReady evidence where available.
- [ ] Let provider-native exact-head GitHub Actions own canonical full-repository verification.
- [ ] Merge, reconcile Work/documentation state, and clean the worktree through KIS.
