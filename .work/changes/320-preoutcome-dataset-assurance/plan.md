# Pre-outcome Dataset Assurance Implementation Plan

**Goal:** Preserve a genuinely blinded confirmatory freeze while retaining exact post-unblinding empirical assurance.

**Architecture:** Add a separate pre-outcome assurance contract in `data_assurance.py`; use it only at confirmatory freeze/open gates. Keep `assert_research_ready()` as the post-unblinding value-level contract and require a binding back to the frozen pre-outcome assurance before result construction.

## Global constraints

- Never read protected WORK-316 settlement outcomes during this change.
- Do not weaken exact reconstruction, semantic verification, or remote preregistration binding.
- Do not modify WORK-316-owned research/provider/test paths.

### Task 1: Evidence first

- Add tests proving pre-outcome assurance is dataframe/value-free and tamper-evident.
- Add tests proving result construction fails without or with mismatched post-unblinding assurance.

### Task 2: Implement lifecycle split

- Add pre-outcome builder/assertion and post-unblinding binding assertion.
- Change freeze/execution gates to consume pre-outcome assurance.
- Change result construction to require post-unblinding research-ready assurance bound to freeze.

### Task 3: Reconcile authority and verify

- Update methodology/rule verification and generated docs.
- Run focused tests, scope check, KIS lifecycle verification/review, exact-head CI, merge and cleanup.
