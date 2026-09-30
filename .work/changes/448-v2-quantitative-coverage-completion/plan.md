# V2 Quantitative Coverage Completion Implementation Plan

> **For agentic workers:** execute inline through the live KIS workflow; TDD is mandatory for every behavior change.

**Goal:** Implement the bounded #448 feature/source contracts and development-only empirical coverage package consumed by #427/#428 without opening protected evidence.

**Architecture:** Add one focused `commodity.v2_coverage` module that owns #448 contract loading, feature-family construction, gates, matched primitive-ablation metadata and execution/result assembly. Extend the existing Databento provider only for PIT open-interest statistics; reuse existing V2 optimization/evaluation utilities rather than changing their scientific semantics.

**Tech Stack:** Python 3.11, pandas, numpy, pytest, existing Commodity V2 optimization/provider interfaces.

**Spec:** `.work/changes/448-v2-quantitative-coverage-completion/spec.md`

## Global Constraints

- Scientific authority is `issue448-prereg-v2.json` SHA `0695fe4944739be2728a70579096e60dab00e7a048232a988faca7adc13de64d` and `issue448-source-feasibility-v2.json` SHA `4e7f63f696097820ed3a6bc2c3b1aaf255744989132d0ac98f4bc7b5605bd7b5`; these supersede the v1 authorities after the no-scoring source-coverage audit and bind the availability-aligned OI lane before empirical scoring.
- Use development evidence only through `2022-12-31`; do not inspect confirmation, prospective paper, SIM, LIVE or V3 evidence.
- Every derived TA family must retain its matched primitive-feature control; algebraic aliases share one family identity.
- PIT inputs use explicit publication/capture timestamps and fail closed when availability is ambiguous.
- Storage market surprise remains HOLD unless all true pre-release consensus gates pass; never substitute seasonal/model expectations.
- Options work is zero-spend feasibility only; no billable acquisition.
- Preserve V1 and existing Databento settlement/volume behavior.

## Review Focus

- Future-row mutation must never alter earlier feature rows.
- Duplicate/non-monotonic availability timestamps must fail closed.
- OI `ts_ref` must not be mistaken for publication availability; `ts_event`/capture availability controls eligibility.
- Missing consensus evidence must stay HOLD rather than becoming a synthetic storage surprise.
- Existing settlement/cleared-volume normalization must remain byte/behavior compatible at its public interface.

---### Task 1: Freeze #448 contract and family identities

**Files:**
- Create: `src/commodity/v2_coverage.py`
- Create: `tests/test_v2_coverage.py`

**Interfaces:**
- Produces `Issue448Contract`, `load_issue448_contract(prereg_path, source_feasibility_path)`, `issue448_family_registry(contract)` and `issue448_source_dispositions(contract)`.
- Later tasks consume the validated contract object and stable family IDs.

- [ ] Write failing tests that load the two exact authoritative artifacts, reject hash/status/cutoff/protected-boundary mutations, and assert the exact preregistered grids plus HOLD/GO/downstream dispositions.
- [ ] Run `python -m pytest tests/test_v2_coverage.py -k "contract or registry or disposition" -q` and verify RED because `commodity.v2_coverage` does not exist.
- [ ] Implement the smallest immutable contract loader/validators and registry projection in `v2_coverage.py`.
- [ ] Re-run the focused tests and verify GREEN.

### Task 2: Add PIT Databento open-interest decoding

**Files:**
- Modify: `src/commodity/providers/databento_futures.py`
- Modify: `tests/providers/test_databento_futures_provider.py`

**Interfaces:**
- Produces `OPEN_INTEREST_STAT_TYPE = 9` and `decode_databento_open_interest_dbn(path, *, dataset=DATABENTO_DATASET) -> tuple[pd.DataFrame, dict[str, Any]]`.
- Output columns: `instrument_id`, `ts_event`, `ts_recv`, `ts_ref`, `quantity`, `stat_type`, `stat_flags`; provenance remains the existing DBN provenance contract.

- [ ] Write failing tests proving stat type 9 is selected, stat types 3/6 are excluded from the OI-specific decoder, `ts_ref` and publication timestamps are preserved, empty/malformed files fail closed, and canonical settlement/volume tests remain unchanged.
- [ ] Run only the new OI tests and verify RED.
- [ ] Implement the dedicated OI decoder by parameterizing/reusing the existing statistics DBN decode path without changing canonical statistics defaults.
- [ ] Run provider focused tests and verify GREEN.### Task 3: Build bounded technical-analysis families

**Files:**
- Modify: `src/commodity/v2_coverage.py`
- Modify: `tests/test_v2_coverage.py`

**Interfaces:**
- Produces `build_issue448_technical_features(market: pd.DataFrame, contract: Issue448Contract) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]`.
- Required raw inputs are `trade_date`, `available_at`, `settle`, `high`, `low`, `close`, `volume`; output feature names are stable `feature_issue448_*` columns grouped by family ID.

- [ ] Write failing tests for EMA/MACD-style, RSI/z-score, Donchian/normalized-range, ATR/Bollinger, ADX/directional movement, and volume-confirmation grids exactly as preregistered.
- [ ] Add tests proving stochastic/Williams aliases share one normalized-range family, primitive controls are declared, future-row mutation cannot change earlier outputs, and bad timestamp order/duplicate availability fails closed.
- [ ] Run focused TA tests and verify RED.
- [ ] Implement deterministic rolling/EMA calculations using only current-and-prior rows available at each timestamp; do not fit data-dependent transforms on future evidence.
- [ ] Re-run focused tests and verify GREEN.

### Task 4: Build PIT market-structure, OI/liquidity and positioning features

**Files:**
- Modify: `src/commodity/v2_coverage.py`
- Modify: `tests/test_v2_coverage.py`

**Interfaces:**
- Produces `build_issue448_market_structure_features(curve, open_interest, positioning, contract) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]`.
- Curve input carries M1..M4 log settlements/DTE/volume at market availability; OI and positioning are joined backward using publication availability, never `ts_ref`/report date alone.

- [ ] Write failing tests for DTE-normalized M1-M2 and M1-M4 basis, 1/5-session basis momentum, preregistered curvature/slope changes, `log_oi_m1`, OI changes, volume/OI, managed-money net % OI and producer/merchant hedging-pressure changes.
- [ ] Add boundary tests proving an OI publication after a decision is invisible and ambiguous/missing publication time remains missing rather than backfilled.
- [ ] Run focused market-structure tests and verify RED.
- [ ] Implement the PIT joins and deterministic feature calculations, reusing existing CFTC semantics where applicable.
- [ ] Re-run focused tests and verify GREEN.### Task 5: Enforce storage/event/options/downstream gates

**Files:**
- Modify: `src/commodity/v2_coverage.py`
- Modify: `tests/test_v2_coverage.py`
- Modify only if executable authority requires: `config/data_sources.json`, `config/research_dataset.json`, `config/models.json`

**Interfaces:**
- Produces `evaluate_issue448_storage_surprise_gate(...)`, `build_issue448_event_timing_features(...)`, `evaluate_issue448_options_preflight(...)`, and `issue448_volatility_tail_handoff(contract)`.

- [ ] Write failing tests that current storage consensus disposition is HOLD, all five activation gates are mandatory, and seasonal/model expectations are explicitly rejected as consensus substitutes.
- [ ] Write failing event tests for hours since/next release and first executable session after public availability, including holiday/exception timestamps supplied by the repository release stream.
- [ ] Write failing options tests proving only local inventory/metadata/zero-dollar quote states can pass preflight and any positive/unknown cost remains HOLD without blocking #448.
- [ ] Write failing handoff tests fixing EWMA/HAR/GARCH plus jump/tail/vol-of-vol and their direction/admission/confidence/risk roles for #427/#428/#430.
- [ ] Implement the gates/features and run focused tests to GREEN.

### Task 6: Execute development-only matched coverage and persist evidence

**Files:**
- Modify: `src/commodity/v2_coverage.py`
- Modify: `tests/test_v2_coverage.py`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-result-v1.json`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-trials-v1.jsonl`
- Modify: `research/programmes/004-v2-maximum-reproducible-one-month-return/evidence-map.json`
- Modify: `research/programmes/004-v2-maximum-reproducible-one-month-return/decisions.json`
- Modify: `research/programmes/004-v2-maximum-reproducible-one-month-return/revisit-triggers.json`

**Interfaces:**
- Produces `run_issue448_development_coverage(...) -> dict[str, object]`, preserving every attempted/held candidate and matched primitive-control identity.

- [ ] Write failing orchestration tests for pre-2023 cutoff, complete attempted-candidate accounting, matched-control identity, HOLD candidates consuming no empirical search, and deterministic result/trial hashes.
- [ ] Implement orchestration by reusing existing #425/#426 chronological outer/inner evaluation utilities; do not create a second backtest engine.
- [ ] Execute only development data through `2022-12-31`, persist the authoritative result/trial ledger, then reconcile programme evidence/decisions/revisit triggers from those results.
- [ ] Run `python -m pytest tests/test_v2_coverage.py tests/providers/test_databento_futures_provider.py -q` and repository-selected KIS verification; fix any review findings before commit/PR.