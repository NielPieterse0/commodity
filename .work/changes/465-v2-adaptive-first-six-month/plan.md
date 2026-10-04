# V2 Adaptive First Six Month Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Implement issue #465 first chronological six-month development block only: consolidate the V2 inventory/PIT state contract, separate causal state from consequence memory, implement a prior-only adaptive controller vertical slice with deterministic block freeze, and produce first-block evidence while keeping later blocks and protected 2023+ confirmation sealed.

**Architecture:** Keep scientific design in the frozen research authority. Repository implementation is a narrow vertical slice: PIT state builder + policy consequence store + prior-only selector + deterministic block-1 runner + tests/evidence. Later blocks and protected 2023+ data remain unreachable from this slice.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific/requirements authority; implementation planning cannot redefine it.
- Use focused tests/verification during development and let the live KIS lifecycle decide what evidence is missing or stale.
- Do not rerun valid implementation evidence merely because the workflow was interrupted.

### Task 1: Map authority to implementation

**Files:**
- Modify: `src/commodity/v2_adaptive_controller.py`, `scripts/research/run_issue465_adaptive_block.py`, frozen issue-465 block-1 research outputs, and this governed change record.
- Test: `tests/test_issue465_adaptive_controller.py`, `tests/test_issue465_adaptive_runner.py`.

- [x] Bind implementation to the L2 optimization line and frozen `issue465-prereg-v1.json`.
- [x] Add acceptance evidence for PIT causality, consequence maturation, seals, duplicate-fill canonicalization, policy-ID handling, and deterministic block freeze.
- [x] Implement the smallest complete block-1 vertical slice and score it once under the frozen procedure.
- [x] Interpret the completed result without changing or rescoring the frozen block-1 selector.
- [ ] Run final KIS exact-source verification and implementation review; resolve implementation findings only.
- [ ] Return to upstream research/design authority for selector redesign before any block-2 access.
