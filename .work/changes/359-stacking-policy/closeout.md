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
- The worktree-local `pyarrow` wheel is present but cannot load because Windows Application Control blocks its native DLL. The current run verified this is an environment-policy defect rather than a repository/scientific defect, installed `fastparquet==2026.5.0` plus `cramjam==2.12.1` only inside the governed worktree `.venv`, and successfully resumed the existing Parquet checkpoints without changing repository dependency authority or scientific semantics.
- Partition `20120101-20121231` is durably checkpointed with 25,363 canonical / 8,664 OHLCV rows, advancing reconstruction to 3 of 13 partitions. A stale older runtime worker was found still consuming CPU without current liveness telemetry; it and a newly spawned duplicate were terminated to restore single-worker execution. The current committed runner was then started as the sole checkpoint owner, reacquired `Phase2CheckpointStore.run_lock()`, revalidated all 39 source inputs, reused the 2010-2012 checkpoints, and is actively reconstructing `20130101-20131231` with fresh telemetry. Before starting any future reconstruction process, first inspect the external runtime telemetry and live process list; if this canonical worker is still alive and emitting heartbeats, monitor it rather than spawning another worker. If no healthy worker remains, rerun `.venv/Scripts/python.exe scripts/research/prepare_phase5_inputs.py` and resume from the latest valid checkpoint. After all inputs materialize, execute `.venv/Scripts/python.exe scripts/research/run_phase5_stacking_policy.py`.

## Residual items

- Frozen WORK-359 handoff still reports `change_id=null` although Work Management correctly reports `change_id=359-stacking-policy`. `bind_task_handoff_change` was attempted with the governed worktree and returned `CANDIDATE_SOURCE_INVALID`; using the repository root returned `CANDIDATE_SOURCE_NOT_GOVERNED`. This does not block current implementation/scoring but must be retried/diagnosed before PromotionReady if the promotion path requires the frozen handoff binding.
- Final Phase-5 scientific result, programme-ledger reconciliation, canonical verification/review closure, PR/CI/merge, and #359 closeout remain pending.
