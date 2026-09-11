# Pit Physical Balance Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Implement and evaluate the frozen Phase-3 compact PIT BHLR production/storage/consumption block against the exact Phase-2 histgb-core-v1 trading-system baseline using only pre-2023 development outcomes, with no BHLR Henry Hub outcome access and no protected-confirmation access.

**Architecture:** Describe only the smallest repository implementation needed. For research-originated work, reference the L3 authority instead of reproducing scientific reasoning.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific/requirements authority; implementation planning cannot redefine it.
- Use focused tests/verification during development and let the live KIS lifecycle decide what evidence is missing or stale.
- Do not rerun valid implementation evidence merely because the workflow was interrupted.

### Task 1: Map frozen Phase-3 authority

**Files:** `config/phase3_fundamentals.json`, `tests/test_fundamentals_phase3.py`

- [ ] Encode issue #357 comment `5626442162`, exact source/member hashes, Phase-2 baseline identity, outer blocks and survival rule.
- [ ] Write RED tests for predictor-only source loading, diagonal vintage indexing, strict PIT joins, and protected-period rejection.

### Task 2: Implement predictor and evaluation pipeline

**Files:** `src/commodity/fundamentals_phase3.py`, `tests/test_fundamentals_phase3.py`

- [ ] Load only the three frozen `BHLR_nowcasts` members; never read BHLR Henry Hub outcomes.
- [ ] Add the latest strictly available monthly physical vintage to Phase-2 market origins.
- [ ] Replay the frozen Phase-2 baseline and fail closed on identity/economic drift.
- [ ] Score the all-three challenger and diagnostic remove-one variants on the same three outer blocks.
- [ ] Report survival, risk, season/regime, side/cost/exposure and PIT diagnostics.

### Task 3: Durable result and lifecycle closeout

**Files:** `research/programmes/003-natural-gas-trading-decision-system/**`

- [ ] Materialize source/code/config identities and `protected_confirmation_accessed=false`.
- [ ] Run focused verification, required review and canonical verification once on the final tree.
- [ ] Commit, PR, exact-head CI, merge, Work Management closeout; return to L3 only for a material scientific change.
