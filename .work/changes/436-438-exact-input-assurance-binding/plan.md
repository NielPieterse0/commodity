# 438 Exact Input Assurance Binding Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Make the #355 provenance boundary fail closed unless one exact decision-input binding joins research-ready assurance evidence to the runtime market, selected-path, and features used by the invocation.

**Architecture:** Keep the correction inside the existing #355 input-boundary seam. The assurance remains the dataset/reconstruction authority. A separate canonical binding joins its immutable assurance identity to runtime role hashes and semantic context. Each runtime role must also be represented by a verified assurance layer and an explicit transformation identity, preventing a binding from laundering an unrelated assurance.

## Global constraints

- Stay inside `scope.json`; `src/commodity/cli.py` is included only to persist the validated binding identity.
- Preserve #355 instrument, roll-policy, partition, protected-confirmation, and deterministic-run behavior.
- Fail closed on malformed hashes, missing/extra role coverage, duplicated/missing assurance layers, absent transformation identities, assurance mismatch, context mismatch, or binding-identity mismatch.
- Do not alter #439, #440, V2 scientific authority, protected evidence, or any `kis-mcp` code/tooling.

### Task 1: Implement exact assurance coverage

**Files:**
- Modify: `src/commodity/trading_decision_v0.py`
- Test: `tests/test_trading_decision_v0.py`

- [x] Reproduce valid-but-unrelated assurance acceptance.
- [x] Require one verified assurance layer per runtime role.
- [x] Require one explicit transformation identity per runtime role.
- [x] Reject partial and mismatched assurance coverage.

### Task 2: Add canonical decision-input binding

**Files:**
- Modify: `src/commodity/trading_decision_v0.py`
- Modify: `src/commodity/cli.py`
- Test: `tests/test_trading_decision_v0.py`

- [x] Bind assurance SHA-256, role/hash identities, instrument, roll policy, and evidence partition.
- [x] Validate the binding SHA-256 and exact role contract.
- [x] Persist the binding SHA-256 in the deterministic run manifest.
- [x] Preserve legitimate deterministic CLI execution.

### Task 3: Verify and close

- [x] Ruff check changed Python files.
- [x] Focused input-boundary tests: 10 passed, 43 deselected.
- [x] Complete affected `test_trading_decision_v0.py` suite: 53 passed.
- [x] Run `pwsh -File scripts/change-workflow.ps1 check`.
- [x] Run repository verification: 757 passed, 7 skipped; all repository checks passed.
- [x] Complete independent code-quality and architecture reviews with full exact-diff evidence; both completed with no findings.
- [ ] Commit, prepare exact-head PR, pass provider CI, merge, and reconcile Work/change records.
