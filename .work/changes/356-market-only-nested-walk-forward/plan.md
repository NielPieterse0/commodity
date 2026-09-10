# Market Only Nested Walk Forward Implementation Plan

**Goal:** implement and freeze the strongest bounded market-only Phase-2 baseline using only pre-2023 development evidence.

## Completed implementation

- [x] Map WORK-356 and the frozen L3 authority into repository scope.
- [x] Return to L3 when the retained daily-bar execution semantics invalidated the original session-open assumption.
- [x] Record the amended execution source/clock in issue #356 comment `5625358200`.
- [x] Reconstruct exact-contract pre-2023 market history without opening 2023+ confirmation.
- [x] Build segmented UTC-day execution paths and prevent five-session targets crossing unpriceable gaps.
- [x] Implement the frozen core/curve feature sets and zero/mean/ridge/constrained-HGB candidate grid.
- [x] Add resumable source/reconstruction/input/fold checkpoints, integrity hashes, locking, telemetry, heartbeats, preflight, and survivor fail-fast gates.
- [x] Canonicalize equivalent duplicate origins to the latest admissible PIT signal and reject conflicting duplicates.
- [x] Complete the nested chronological development run and freeze `histgb-core-v1`.
- [x] Materialize Programme 003 canonical research evidence.

## Closeout

- [ ] Run change-workflow/methodology checks and canonical verification once on the final tree.
- [ ] Perform one final code-quality review; repeat only if a real blocking finding requires a fix.
- [ ] Commit, prepare PR, require exact-head CI, merge, reconcile WORK-356/#356, and clean the worktree.
