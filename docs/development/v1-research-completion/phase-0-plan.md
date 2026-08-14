# V1 Phase 0 Merge-Gate Implementation Plan

> **For agentic workers:** Load any required execution sub-skill through the canonical KIS MCP Skills module by logical skill ID. Steps use checkbox syntax for tracking.

**Goal:** Close external-review blockers #1–#6, #17, A1, A2, A4, F1, H1, and K1 before Phase A begins.

**Architecture:** Convert declarative governance into fail-closed executable contracts at existing module boundaries. Keep configuration as the single owner, provider-neutral canonical rows as the market boundary, and experiment records as the reproducibility/evaluation boundary.

**Tech Stack:** Python 3.11+, pandas, NumPy, scikit-learn, pytest, Ruff, JSON Schema, setuptools.

## Global Constraints

- No paid Databento acquisition or network retrieval.
- No LIVE trading authorization; explicit human approval remains absent.
- Behavior changes are test-first and fail closed.
- Preserve provider-neutral futures interfaces and PIT semantics.
- Keep authoritative mutable values in their existing config owners.

---

### Task 1: Roll-policy executable contract

**Files:** create `src/commodity/roll_policy.py`; modify `src/commodity/rolls.py`, `src/commodity/market_data.py`; test `tests/test_rolls.py`, `tests/test_market_data.py`.

**Produces:** one parser/validator for all declared `continuous_series_policy.policy` semantics, consumed by readiness and roll execution.

- [ ] Add failing tests proving every declared semantic is required and unsupported semantic values block execution/readiness.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement the typed roll-policy contract; remove duplicated expected-policy literals from readiness.
- [ ] Run focused tests to green and commit.

### Task 2: Canonical market and PIT-join boundary

**Files:** modify `src/commodity/research_dataset.py`, `src/commodity/availability.py`; test `tests/test_research_dataset.py`, `tests/test_availability.py`.

**Produces:** canonical-contract dataset input and explicit grouped PIT joins.

- [ ] Add failing tests that canonical mode rejects proxy OHLCV and accepts provider-neutral canonical contract rows.
- [ ] Add failing tests proving independent exogenous series cannot cross-match and ambiguous grouping fails closed.
- [ ] Implement canonical contract-to-selected-market dataset construction and explicit `by` grouping support.
- [ ] Run focused tests to green and commit.

### Task 3: Reproducible environment and installed config

**Files:** modify `src/commodity/config.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `requirements.lock.txt`, `README.md`; add config/package tests.

**Produces:** installed config-data resolution plus one dependency lock actually used by CI/bootstrap.

- [ ] Add failing tests for config resolution without source-tree assumptions and for lock/install contract shape.
- [ ] Package root-owner config files as distribution data without duplicating source authority.
- [ ] Install the exact lock in CI/bootstrap, then install the project editable/noneditable with `--no-deps` as appropriate.
- [ ] Remove the non-default-index local torch version marker from the lock.
- [ ] Run focused packaging/config tests to green and commit.

### Task 4: Valid walk-forward split contract (#17)

**Files:** modify `config/experiment.json`, `src/commodity/evaluation.py`/`tournament.py` as needed; test `tests/test_tournament.py`, CLI tests.

**Produces:** a configured initial window that is valid for the verified canonical-history boundary and a fail-closed non-empty-OOS guard.

- [ ] Add a failing test for `initial_train >= available rows` and one against the canonical verified-history sample size.
- [ ] Implement the OOS guard and revise the owner config to a defensible initial window while retaining expansion/retraining semantics.
- [ ] Run focused tests to green and commit.

### Task 5: Databento quarantine and integrity governance

**Files:** modify `config/data_sources.json`; add a safe evidence/quarantine manifest under `docs/development/databento-full-history-acquisition/`; test data-source governance.

**Produces:** authoritative quarantine state that prevents the existing ~$39.65 acquisition from being used as research/canonical evidence until integrity is complete.

- [ ] Add failing tests that incomplete integrity/quarantined Databento evidence cannot be promoted.
- [ ] Record local acquisition identity, cost, verified fraction/status, quarantine reason, and no-redownload decision without licensed values or secrets.
- [ ] Update the config owner first to reference the quarantine/evidence status and keep `backtest_evidence_allowed=false`.
- [ ] Run focused tests to green and commit.

### Task 6: Research contract, leakage, and significance

**Files:** modify `src/commodity/evaluation.py`, `src/commodity/tournament.py`, `src/commodity/records.py`, `src/commodity/cli.py`; tests in pipeline/tournament/records.

**Produces:** paired time-series uncertainty/significance, strong future-label invariance checks, and schema-v2 experiment-record output for tournament runs.

- [ ] Add failing tests that mutate every future label segment and assert all earlier forecasts remain invariant.
- [ ] Add failing paired-comparison tests with block-bootstrap confidence intervals and a conservative null decision.
- [ ] Add failing CLI/record tests requiring tournament output to emit a schema-valid experiment contract with leakage/significance fields populated.
- [ ] Implement the minimum deterministic evaluation/recording path and run focused tests to green.
- [ ] Commit after focused verification.

### Task 7: Enforceable LIVE human-approval gate

**Files:** modify `config/policy.json`, `src/commodity/policy.py`; test policy behavior.

**Produces:** LIVE execution requires both policy permission and a complete explicit-human-approval record; default config remains prohibited.

- [ ] Add failing tests showing `live_trading_allowed=true` alone is insufficient and incomplete approval evidence fails closed.
- [ ] Add explicit approval fields to the policy owner with an unapproved default and validate them in `assert_execution_mode`.
- [ ] Confirm offline/simulation/paper behavior is unchanged and LIVE remains blocked.
- [ ] Run focused tests to green and commit.

### Task 8: Phase 0 closeout gate

**Files:** update `phase-0-review.md` plus bounded evidence files only after implementation verification.

**Produces:** exact-head verification and independent diff review evidence that maps every gate finding to code/tests/evidence.

- [ ] Run all focused suites, full pytest, Ruff, packaging checks, and `git diff --check`.
- [ ] Request independent code-quality, architecture/API-contract, test-quality, and safety review on the exact Phase 0 diff.
- [ ] Fix every blocking or important finding and rerun affected verification.
- [ ] Record the exact closure map for #1–#6, #17, A1, A2, A4, F1, H1, K1.
- [ ] Only after the gate is clean, begin Phase A implementation from this exact verified head.
