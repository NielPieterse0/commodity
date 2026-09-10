# Closeout: Market Only Nested Walk Forward

## Implemented scope

- Implemented the pre-2023 market-only nested walk-forward baseline and canonical Programme-003 evidence.
- Added segmented exact-contract UTC-day execution, PIT features, nested selection, cost/risk diagnostics, and frozen baseline output.
- Added resumable hash-bound checkpoints, telemetry/heartbeats, run locking, structural preflight, one-origin-per-fill canonicalization, survivor fail-fast gates, and code-bound cache identities.

## Implementation evidence

- Successful development run: 2,865 unique executable origins; 80/80 structural preflight checks; 86/86 current score checkpoints passed.
- Frozen candidate: `histgb-core-v1`; freeze SHA-256 `38225498e910b9a1fa76093e043701b8cada4ed5e70fc40bc5aa890f914eec9d`.
- Development nested net P&L: +$16,370; final-candidate outer aggregate: +$26,040; maximum drawdown: 7.66%.
- Canonical verification: 570 passed, 7 skipped; all repository checks and Git whitespace passed.
- Protected 2023+ confirmation remained unopened; result is development evidence only.

## Research return

- L3 authority: issue #356 comments `5621959654` and execution-source amendment `5625358200`.
- Canonical result: `research/programmes/003-natural-gas-trading-decision-system/phase2-market-only-baseline-v1.json`.
- Phase 3 must compare PIT fundamentals against this frozen market-only baseline.

## Delivery pending

- Final code-quality review, commit, exact-head PR/CI, merge, WORK-356/#356 reconciliation, and worktree cleanup.
