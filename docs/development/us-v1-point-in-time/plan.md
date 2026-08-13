# U.S. V1 Point-in-Time Availability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for behavior changes and superpowers:verification-before-completion before any completion claim.

**Goal:** Build a configuration-driven availability/evidence layer that supports leakage-aware U.S. V1 research while keeping canonical gates fail-closed.

**Architecture:** Add a focused `commodity.availability` module for provider timing annotation, evidence-mode validation, and point-in-time joins. Keep source-specific schedules and exception coverage in `config/data_sources.json`; current snapshot revision limitations remain explicit metadata rather than being hidden by the transformation layer.

**Tech Stack:** Python 3.11+, pandas, zoneinfo, pytest, JSON configuration.

## Global Constraints

- Massive licensing, redistribution, and canonical market-evidence gates remain unchanged.
- Unknown historical availability is never silently treated as exact.
- Current historical snapshots remain noncanonical when revision vintages cannot be reconstructed.
- No serious model training or LIVE execution changes.

---

### Task 1: Availability contract and evidence modes

**Requirements:** R1, R5, R6
**Files:**
- Create: `src/commodity/availability.py`
- Create: `tests/test_availability.py`

**Interfaces:**
- `validate_availability(frame: pd.DataFrame, mode: str) -> pd.DataFrame`
- `asof_join_point_in_time(cutoffs: pd.DataFrame, exogenous: pd.DataFrame, value_columns: list[str], mode: str = "research_pit", cutoff_col: str = "prediction_time") -> pd.DataFrame`

**Test-first behavior:**
- reject unknown modes;
- `canonical` accepts only verified availability + point-in-time revision state;
- `research_pit` accepts verified or conservative timing only when revision-safe;
- `screening` may accept conservative timing with current-snapshot revisions but retains noncanonical risk labels;
- all modes reject missing availability for rows they would otherwise consume;
- as-of joins cannot select future rows.

**Review gate:** Evidence tiers cannot be confused with trading authority or Massive canonical permission.

**Verification:** `python -m pytest tests/test_availability.py -q`.

### Task 2: EIA-930 timing reconstruction

**Requirements:** R2, R7
**Files:**
- Modify: `src/commodity/availability.py`
- Modify: `config/data_sources.json`
- Modify: `tests/test_availability.py`

**Interfaces:**
- `annotate_eia930_region_availability(frame: pd.DataFrame, source_cfg: dict) -> pd.DataFrame`
- `annotate_eia930_generation_availability(frame: pd.DataFrame, source_cfg: dict) -> pd.DataFrame`

**Test-first behavior:**
- hourly demand becomes available only after the completed operating hour plus the configured reporting lag;
- demand forecast uses a DST-aware America/New_York morning cutoff;
- prior-day generation uses a DST-aware next-day morning cutoff;
- all reconstructed EIA-930 rows are marked conservative and current-snapshot revision-bearing.

**Review gate:** No local-time arithmetic may be done with a fixed UTC offset.

**Verification:** targeted EIA-930 tests plus full `tests/test_availability.py`.

### Task 3: WNGSR release reconstruction

**Requirements:** R3, R7
**Files:**
- Modify: `src/commodity/availability.py`
- Modify: `config/data_sources.json`
- Modify: `tests/test_availability.py`

**Interfaces:**
- `annotate_wngsr_availability(frame: pd.DataFrame, source_cfg: dict, observed_col: str = "period") -> pd.DataFrame`

**Test-first behavior:**
- regular week-ending Friday maps to the following Thursday 10:30 Eastern;
- official configured exception dates override the regular release timestamp;
- dates before configured exception-registry coverage are marked unresolved unless explicitly overridden;
- current historical storage values remain revision-bearing and therefore unavailable to `canonical`/`research_pit` without vintage reconstruction.

**Review gate:** Release-time reconstruction must not be mistaken for original-value reconstruction.

**Verification:** targeted WNGSR tests.

### Task 4: Archived weather research timing

**Requirements:** R4, R5, R7
**Files:**
- Modify: `src/commodity/availability.py`
- Modify: `config/data_sources.json`
- Modify: `tests/test_availability.py`

**Interfaces:**
- `annotate_weather_research_availability(frame: pd.DataFrame, source_cfg: dict) -> pd.DataFrame`

**Test-first behavior:**
- source `issued_at` is preserved;
- conservative research availability is `issued_at + configured global-model lag + consistency margin`;
- exact historical source availability remains unverified;
- immutable issued-run values may be `research_pit` eligible but never `canonical` solely from this reconstruction.

**Review gate:** No reanalysis or forecast-valid timestamp may substitute for issued-run availability.

**Verification:** targeted weather tests plus existing `tests/test_weather.py`.

### Task 5: Current-state reconciliation and closeout

**Requirements:** R7, R8
**Files:**
- Modify: `README.md`
- Modify: `docs/data-manifest.md`
- Modify: `config/data_sources.json`
- Create: `docs/development/us-v1-point-in-time/review.md`

**Behavior:** Document which U.S. V1 sources are usable for screening, which qualify for `research_pit`, and which remain blocked by revision/vintage reconstruction. Keep Massive licensing unchanged.

**Review gate:** Diff review must confirm no stale claim says the entire U.S. V1 dataset is canonical or point-in-time complete.

**Verification:**
- `python -m pytest -q`
- `python -m ruff check .`
- `git diff --check`
- fresh GitHub CI on the PR head.

## Ordered dependencies

Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5.

## Recovery

All changes are additive/configuration-driven on an isolated feature branch. Revert the PR or individual commits to restore the previous preservation-only state; no raw snapshots or persistent database migrations are modified.
