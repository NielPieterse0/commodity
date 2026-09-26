# V2 Storage Weather Fundamentals Cross Market Implementation Plan

**Goal:** Execute #426 without crossing the pre-2023 development boundary and produce a reproducible result even when admissible exogenous evidence is unavailable.

**Architecture:** Extend the existing V2 optimizer with a source-readiness gate, PIT-safe exogenous as-of join, matched market+family feature preparation, deterministic snapshot-coverage identity, and a result builder that binds #425 as the control. Do not create a second optimization framework.

## Global constraints

- Work only in the governed #426 worktree.
- Use only development evidence through 2022-12-31 for scoring/selection.
- Treat `config/data_sources.json` as source-admissibility authority.
- Keep 2023+ confirmation, paper, SIM and LIVE evidence unopened.
- Use the worktree-local `.venv` and repository direct Python runner.

## Task 1: Freeze #426 execution contract

- [x] Add `issue426-search-plan-v1.json` before #426 scoring.
- [x] Bind the core PIT families, matched #425 control, interactions, reporting, HOLD rules and revisit triggers.
- [x] Correct the stale V2 registry status from registration-only to active optimization execution.

## Task 2: Implement source and feature boundaries

- [x] Add deterministic source-gate logic for storage, weather, power and positioning.
- [x] Inventory preserved snapshot coverage without reading outcomes.
- [x] Add backward-only bounded-staleness PIT joins.
- [x] Add market-control-plus-family feature preparation.
- [x] Add RED/GREEN tests for cutoff, future-data rejection, transforms and source-gate behavior.

## Task 3: Acquire and execute admissible historical evidence

- [x] Acquire and integrity-bind pre-2023 EIA WNGSR first-published storage evidence and CFTC Henry Hub disaggregated positioning evidence.
- [x] Build resumable historical GFS 0.25 issued-run acquisition with immutable daily manifests, hashes, explicit archive omissions and conservative availability timing.
- [x] Freeze weather-feature and storage × weather × season × volatility interaction semantics before either can be scored.
- [x] Enforce representation-specific training support and common-inner-fold comparison so unequal source history cannot bias representation selection.
- [x] Hold PJM power before scoring because historical publication-lag semantics are not yet defensibly promoted.
- [x] Complete all 2,908 issued-weather days, pass the complete source gate, then score weather and the registered combined interaction.
- [x] Persist the final `issue426-result-v1.json` plus durable `issue426-trials-v1.jsonl` from the clean authoritative 667-trial ledger and regenerate deterministic reference documentation.

Current execution state: storage, positioning and all 2,908 issued-weather days pass the strengthened PIT/integrity gates. The authoritative development optimization completed with 667 trial records; storage and positioning retain matched marginal value, standalone weather is held, and the preregistered storage × weather × season × volatility interaction retains matched marginal value. PJM power remains held for unresolved historical publication-lag semantics. Protected confirmation, forward, paper, SIM and LIVE evidence remain unopened.

## Task 4: Verification and delivery

- [ ] Run focused source/tests/configuration/documentation checks selected by KIS.
- [ ] Run independent code-quality review and close material findings.
- [ ] Commit the exact verified tree.
- [ ] Prepare PR, observe exact-head CI, merge, reconcile Work/documentation state and clean the worktree through KIS.
