# Tasks: V2 Target Horizon Market State

- [x] Confirm live KIS authority, classification, scope, required skills, and required artifacts.
- [x] Map #399/#400 plus the landed V2 registry into the bounded repository change without duplicating upstream authority.
- [x] Implement the pre-score #425 search/optimization path with focused tests (`11 passed`).
- [x] Freeze the executable code/search-plan bytes before scoring (`issue425-search-plan-v1.json` last write 19:50:28; `v2_optimization.py` last write 19:55:22; canonical runner start 19:57:45). Commit `70ee549f...` recorded those unchanged bytes at 20:32:29 and must not be described as a pre-score commit.
- [x] Run/resume the development-only optimization and persist the complete attempt/result evidence; retain the duplicate-runner finding (two identical duplicate ledger records, no score/config divergence) as an operational hardening item before #426. Final result: `complete_development_only`, 2,199 unique trials, protected confirmation/forward/SIM/LIVE untouched.
- [x] Run `pwsh -File scripts/change-workflow.ps1 check` after result artifacts are reconciled; passed on 2026-09-15.
- [ ] Use the live KIS lifecycle decision and execute only missing/invalid implementation verification or review evidence. Local verification is green (`11 passed` focused; `712 passed, 7 skipped`, all repository checks passed) after regenerating required docs; KIS aggregate execution hit a transient upstream 502 and should be retried.
- [ ] Prepare the reviewable PR from valid PromotionReady evidence where available.
- [ ] Let provider-native exact-head GitHub Actions own canonical full-repository verification.
- [ ] Merge, reconcile Work/documentation state, and clean the worktree through KIS.
