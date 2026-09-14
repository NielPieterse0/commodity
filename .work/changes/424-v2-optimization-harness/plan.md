# V2 Optimization Harness Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Implement the development-only V2 optimization execution harness, trial ledger, common monthly score engine, frozen V1 comparator, conditional search support, and bounded resumable pilot required by issue #424 without accessing protected confirmation, prospective paper, Saxo SIM, or LIVE evidence.

**Architecture:** Add a single reusable `commodity.v2_optimization` module that validates the authoritative registry boundary, creates deterministic trial identities, persists an idempotent JSONL trial ledger, expands bounded registry axes, scores chronological paper-replay paths by monthly economics, and binds the frozen V1 comparator by content identity. Durable pilot evidence lives under Programme 004; no existing V1 logic is modified.

## Global constraints

- Stay inside `scope.json`.
- Preserve `config/v2_variable_registry.json` as authority; consume it read-only.
- Never search or score `reserved_confirmation` or `true_forward` evidence.
- Keep the pilot cutoff at or before `2022-12-31` and do not use the post-2022 V1 benchmark as search evidence.
- Use focused tests first, then a bounded development pilot, then KIS-selected verification/review.

### Task 1: Harness contracts and tests

**Files:**
- Add: `src/commodity/v2_optimization.py`
- Add: `tests/test_v2_optimization.py`

- [x] Test evidence-boundary rejection and registry-axis validation.
- [x] Test deterministic trial IDs, idempotent resume, and conflicting duplicate rejection.
- [x] Test monthly score diagnostics and chronology validation.
- [x] Test frozen V1 identity binding without mutation.

### Task 2: Programme-004 pilot evidence

**Files:**
- Add: `research/programmes/004-v2-maximum-reproducible-one-month-return/**`

- [x] Register Programme 004 / execution line identity.
- [x] Run a bounded pre-2023 development pilot using retained exact-source inputs or already-development-class replay evidence.
- [x] Persist trial ledger, pilot manifest/result, identities, search budget, pruning disposition, and explicit evidence boundary.
- [x] Invoke the same pilot again and prove completed trials are skipped rather than duplicated.

### Task 3: Verification and delivery

- [ ] Run focused tests and change checks.
- [ ] Obtain independent review if the configured review backend is available.
- [ ] Commit through KIS and prepare the exact-tree PR.
- [ ] Require provider-native exact-head CI before merge.
