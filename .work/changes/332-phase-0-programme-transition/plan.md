# Phase 0 Programme Transition Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Close and transfer Programme 002 into one authoritative Phase 0 handoff baseline for the forecast programme without executing any new empirical experiment.

**Authority:** GitHub issue #332 defines the transition acceptance criteria. `research/programmes/002-henry-hub-fresh/**` remains scientific authority; `config/research_methodology.json` owns repository research lifecycle semantics.

## Global constraints

- No empirical outcome execution or protected confirmation opening.
- Preserve literature, feasibility, PIT/source contracts, data assurance, chronology, leakage controls, provenance, OOS discipline and search history.
- Do not weaken confirmatory preregistration, freeze, sealed-window or post-unblinding assurance gates.
- No new paid-data acquisition or infrastructure.
- Generated documentation is regenerated from canonical JSON owners.

### Task 1: Lock transition behavior with regression evidence

**Files:** `tests/research/test_phase0_programme_transition.py`

- [x] Assert all 21 designs receive exactly one forecast-objective role.
- [x] Assert historical 14 GO / 7 HOLD and zero-outcome boundary remain preserved.
- [x] Assert Phase 1 uses governed exploratory schema-v3 without preregistration on development/research-OOS data.
- [x] Confirm the test fails because the transition authorities are absent.
### Task 2: Establish the authoritative Programme 002 handoff

**Files:** `research/programmes/002-henry-hub-fresh/research-synthesis.json`, `programme.json`, `l0-l3-closeout.json`, `implementation-readiness.json`

- [ ] Record what the original programme established and did not establish.
- [ ] Carry forward Agent A verified pre-outcome implementation and Agent B landed source/data-assurance work by exact identities.
- [ ] Reclassify 21 designs as forecast candidate, contextual evidence, unavailable exact replication, or no-longer-worth-pursuing.
- [ ] Define the exact Phase-1 starting sequence and non-critical paid-data boundary.

### Task 3: Remove the obsolete exploratory freeze blocker

**Files:** `config/research_methodology.json`

- [ ] Make the existing schema-v3 exploratory path explicit for pre-proof development and rolling research OOS.
- [ ] Keep reserved/sealed confirmation protected behind confirmatory freeze.
- [ ] Retain PIT, provenance, reconstruction, semantic, data-assurance, chronology, leakage and search-history controls.

### Task 4: Generate, verify, review and land

- [ ] Regenerate owned documentation from canonical JSON.
- [ ] Run focused transition tests and affected research checks.
- [ ] Run governed scope check and full canonical verification.
- [ ] Resolve specialist review findings, prepare exact PR, pass GitHub Actions, merge, reconcile Work/docs, and clean the worktree.
