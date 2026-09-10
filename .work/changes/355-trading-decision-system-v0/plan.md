# Trading Decision System V0 Implementation Plan

> Execute through the live KIS lifecycle; scientific authority remains GitHub issue #355 comment `5611074612`.

**Goal:** implement the smallest complete repository path satisfying `WORK-355` without opening protected confirmation or introducing live execution authority.

**Architecture:** keep model forecasting, signal policy, and execution/risk accounting separate. Reuse existing roll-safe market semantics; add a dedicated Phase-1 decision-system path rather than changing legacy simulation behavior.

## Implementation sequence

1. Freeze operator-owned risk policy in `config/trading-policy.json`; keep it non-model-tunable.
2. Define the decision-system execution/cost contract in `config/simulation.json`; require explicit per-run unverified broker assumptions instead of inventing fees/margin.
3. Complete the simple forecast ladder in `config/models.json`.
4. Implement exact-contract five-session target construction and realized-label-only chronological forecasting in `src/commodity/trading_decision_v0.py`.
5. Implement single-net-position signal translation, fill/roll/cost accounting, margin gating, loss/drawdown kill, and persistent killed state.
6. Add `commodity trading-decision-v0` orchestration with deterministic input/config hashes and run outputs.
7. Prove roll-gap exclusion, PIT-safe fills, non-overlap leverage, risk immutability, benchmark parity, and byte-reconstructable outputs in focused tests.
8. Run repository/KIS-selected verification and independent reviews; fix only findings that preserve the frozen L3 contract.
9. Commit, derive PromotionReady, prepare the exact PR, then use provider-native CI and KIS closeout/merge workflows.

## Recovery

All implementation is isolated to the governed #355 worktree. If a material scientific ambiguity appears, preserve current evidence and return to the owning L3 authority. If implementation verification fails, fix within the same change and rerun only invalidated evidence.
