# Phase A Canonical Market Structure Implementation Plan

> **For agentic workers:** Load any required execution sub-skill through the canonical KIS MCP Skills module by logical skill ID. Steps use checkbox syntax for tracking.

**Goal:** Convert provider-neutral canonical NG contract rows into deterministic PIT-safe roll and curve features with auditable lineage.

**Architecture:** Keep provider adapters unchanged. `market_data.py` owns explicit availability preservation/reconstruction and cutoff-safe curve derivation. `research_dataset.py` composes the owned roll path, return-neutral derived market representation, within-contract target, complete M1–M4 curve features and deterministic lineage. Licensing readiness remains an independent fail-closed gate.

**Tech Stack:** Python, pandas, pytest, Ruff; existing JSON configuration and SHA-256 lineage helpers.

## Global Constraints
- Raw per-contract rows remain canonical; the continuous series is derived only.
- No cross-contract return is emitted.
- `available_at <= prediction_time` for every curve value.
- No vendor-specific dependency in core market/dataset logic.
- No paid acquisition, licensing promotion, or LIVE authority change.

---

### Task 1: PIT-safe market-structure derivation

**Files:** `tests/test_market_data.py`, `src/commodity/market_data.py`

**Produces:** `build_market_structure_features(frame, schema, prediction_cutoffs, max_contracts=4) -> tuple[pd.DataFrame, pd.DataFrame]` plus explicit canonical availability reconstruction/preservation.
- [x] Add tests for cutoff filtering, ranks, spreads, slope, and missing availability.
- [x] Run the targeted market-data tests and confirm the new tests fail for the intended reason.
- [x] Implement the cutoff-safe curve builder and derived numeric features.
- [x] Run `tests/test_market_data.py` and keep it green.

### Task 2: Canonical dataset composition and lineage

**Files:** `tests/test_research_dataset.py`, `src/commodity/research_dataset.py`

**Consumes:** canonical contract rows, owned roll policy, Task 1 curve features.
**Produces:** canonical PIT dataset containing `market_structure` plus deterministic lineage hashes.

- [x] Add tests for canonical market-structure columns/family and unavailable quote rejection.
- [x] Add a deterministic-lineage test for contract input, roll path, ledger, curve artifact and policy hash.
- [x] Run targeted dataset tests and confirm the new tests fail.
- [x] Implement canonical composition and lineage; keep research-PIT proxy behavior unchanged.
- [x] Run dataset and roll tests and keep them green.
### Task 3: Phase A evidence and closeout

**Files:** `docs/development/v1-research-completion/phase-a-evidence.json`, `docs/development/v1-research-completion/phase-a-review.md`

- [x] Run the derivation twice against the preserved local Massive canonical snapshot and compare hashes.
- [x] Record rows, curve coverage, roll count, hashes and the licensing/promotion status from `config/data_sources.json`.
- [x] Record Databento as quarantined and state whether any integrity-verified overlapping period exists; do not use quarantined values as research evidence.
- [x] Run full pytest, Ruff, `git diff --check`, and the repository secret-pattern scan.
- [x] Run independent code/architecture review on the exact final diff; fix blocking findings and rerun affected checks.
- [ ] Commit the exact reviewed Phase A change and synchronize GitHub/KIS work records without closing later phases.

## Recovery
All runtime changes are isolated on `feat/v1-phase-a-market-structure`. Revert the Phase A commit to return to the verified Phase 0 checkpoint; ignored raw snapshots are read-only evidence inputs and are not modified.
