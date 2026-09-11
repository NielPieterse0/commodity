# Closeout: Stacking Policy

## Implemented scope

- Frozen the Phase-5 36-configuration stacking-policy contract before scoring.
- Implemented bounded long/short/flat specialist modifiers, uncertainty calibration, explicit position-change costs, risk-shutdown attribution, continuous no-kill replay, nested chronological selection helpers, and executable research runners.
- Protected 2023+ confirmation remains unopened.

## Implementation evidence

- Checkpoint commits: `80f0d6e788ef117c97aee77c8ae9977a605d2c81`, `e44ea0eb23970296a3af7b63e4f5830c494c6862`.
- Focused verification: `12 passed` for `tests/test_stacking_policy.py`; Python compile passed; `scripts/change-workflow.ps1 check` passed after runtime-state relocation.
- Pre-execution review: KIS code-quality review on `b67e550..80f0d6e` returned no findings.
- PromotionReady / reusable evidence: not yet due; scientific scoring and final evidence remain incomplete.

## Provider and landing evidence

- Pull request exact head:
- Provider-native GitHub Actions:
- Merge / landed revision:
- Documentation / Work reconciliation:
- Cleanup:

## Research return, when applicable

- Upstream L3 authority:
- Exact implementation/landing identity returned to research lineage:
- Any scientific escape/re-entry:

## Current execution checkpoint

- Canonical Phase-2 input reconstruction uses external runtime state at `C:/Projects/commodity/.work/runtime/359-stacking-policy/phase5-inputs` so checkpoints do not contaminate the governed worktree.
- Global NG definition authority is checkpointed and reused.
- Partitions `20100606-20101231` and `20110101-20111231` are durably checkpointed. The first contains 14,775 canonical / 5,131 OHLCV rows; the second contains 25,922 canonical / 8,418 OHLCV rows. Reconstruction reports 13 total partitions.
- Duplicate pre-lock workers discovered in telemetry were explicitly terminated; the retained implementation now acquires `Phase2CheckpointStore.run_lock()` before reconstruction.
- The run was deliberately stopped at the second partition boundary with no worker left running. Next action: rerun `python scripts/research/prepare_phase5_inputs.py`; the run lock and checkpoint store should resume from the 2012 partition. After all inputs materialize, execute `python scripts/research/run_phase5_stacking_policy.py`.

## Residual items

- Frozen WORK-359 handoff still reports `change_id=null` although Work Management correctly reports `change_id=359-stacking-policy`. `bind_task_handoff_change` was attempted with the governed worktree and returned `CANDIDATE_SOURCE_INVALID`; using the repository root returned `CANDIDATE_SOURCE_NOT_GOVERNED`. This does not block current implementation/scoring but must be retried/diagnosed before PromotionReady if the promotion path requires the frozen handoff binding.
- Final Phase-5 scientific result, programme-ledger reconciliation, canonical verification/review closure, PR/CI/merge, and #359 closeout remain pending.
