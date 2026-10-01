# V2.32 Execution Structure Optimization Implementation Plan

> **Execution:** native in this governed worktree; TDD for behavior changes and no-scoring preflight before empirical evaluation.

**Goal:** Explain the #459 advantage by controlled removals, then improve it through bounded lifecycle/execution changes without opening protected confirmation.

**Architecture:** Reuse the #428/#459 PIT-safe opportunity builder, specialist joins, replay engine, and scoring. The #429 runner reconstructs the promoted control, applies deterministic contribution ablations or chronological decision-stream transforms, and records matched outer/cost trials.

## Global constraints

- Development only through 2022-12-31.
- Exact #459 Wave 2 v2 control is the parent comparator.
- No sizing/leverage search; that remains #430.
- No synthetic event-time lane while #448 timing remains HOLD.
- Forecasts and origin rows stay fixed for retained decision-context ablations.
- All trials use inherited risk kills and base/1.5x/2x cost profiles.

### Task 1: Freeze #429 authority

**Files:**
- Create: `.work/changes/429-v2-entry-exit-holding-position-structure/spec.md`
- Create: `.work/changes/429-v2-entry-exit-holding-position-structure/plan.md`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue429-prereg-v1.json`

- [ ] Bind exact #459 parent/result/ledger identities and development cutoff.
- [ ] Freeze removal ablations, execution variants, promotion gates, cost profiles, and event-time HOLD.

### Task 2: Execution-transform TDD

**Files:**
- Create: `tests/test_issue429_execution_structure.py`
- Create: `scripts/research/run_issue429_execution_structure.py`

- [ ] Write failing tests for deterministic variant identities and chronological decision transforms.
- [ ] Cover abstain-hold, same-direction ignore, opposite exit-only, delayed entry, fixed-hold caps, and one-per-target-window behavior.
- [ ] Prove transforms never cross the protected cutoff, never use an unavailable timestamp, and never create duplicate decisions.
- [ ] Implement only the minimal runner primitives required by the tests.

### Task 3: No-scoring preflight and contribution ablations

**Files:**
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue429-preflight-v1.json`

- [ ] Verify #448 cache and #459 parent/specialist/source identities, rows, safety, costs, and trial budget.
- [ ] Reproduce the promoted control construction without scoring during preflight.
- [ ] Score all declared component removals across both outers and all inherited cost profiles.
- [ ] Record removal effects versus the full promoted control with exact effective-sample and risk diagnostics.

### Task 4: Lifecycle scoring and disposition

- [ ] Score every frozen lifecycle variant across both outers and all cost profiles.
- [ ] Compare each directly with the reproduced #459 control on identical development blocks.
- [ ] Apply the frozen economic, cross-outer, cost, sample, concentration, and kill-regression gates.
- [ ] Write deterministic `issue429-trials-v1.jsonl` and `issue429-result-v1.json`.

### Task 5: Verification and closeout

- [ ] Run focused tests and Ruff during implementation.
- [ ] Run canonical `scripts/verify.ps1` and deterministic artifact regeneration checks.
- [ ] Close KIS code/test review findings, commit, PR, exact-head CI, merge, reconcile, and clean the worktree.
