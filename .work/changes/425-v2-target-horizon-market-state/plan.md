# V2 Target Horizon Market State Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Execute V2.28 development-only optimization for target/horizon choices and market-state feature/transform families for Programme #393 from the frozen WORK-425 handoff, without opening protected 2023+ confirmation, prospective paper, Saxo SIM, or LIVE evidence.

**Architecture:** Extend the landed #424 V2 harness in `src/commodity/v2_optimization.py`; keep the #425 search contract in Programme 004 and write all scored attempts to a resumable content-bound trial ledger.

## Global constraints

- Stay inside `scope.json` and the #399/#400 registrations plus the landed V2 registry.
- Freeze search-plan/code identity before the first #425 score is written.
- Selection is chronological and inner-only; no data later than `2022-12-31` may be used.
- Preserve all completed/failed trials and resume by deterministic trial identity.
- Do not reinterpret later-family work owned by #426-#431 into this change.

### Task 1: Freeze executable #425 search

**Files:** `issue425-search-plan-v1.json`, `src/commodity/v2_optimization.py`, `tests/test_v2_optimization.py`

- [x] Bind #399/#400 and the landed V2 registry.
- [x] Implement registered target/horizon, bounded market-state, transform, and required interaction search.
- [x] Add focused evidence-boundary, plan, transform, target, scoring, and resumption tests.
- [x] Run focused tests before scoring (`11 passed`).
- [ ] Commit the pre-score search/code identity through KIS.

### Task 2: Execute and retain development evidence

- [ ] Run/resume the #425 development optimization with the committed pre-score identity.
- [ ] Persist trial ledger, result, controls, V1 development comparator, failures/prunes, and protected-evidence flags.
- [ ] Update generated Programme 004 documentation when canonical research evidence changes.
- [ ] Run affected verification/review and resolve material findings.
- [ ] Continue through KIS PromotionReady/PR/CI/merge/Work reconciliation when evidence permits.
