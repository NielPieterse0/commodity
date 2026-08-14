# Phase B PIT Exogenous-Family Implementation Plan

**Goal:** Turn storage, weather, power, and positioning into explicit PIT research decisions with deterministic lineage and fail-closed blockers.

**Architecture:** Keep availability rules in `commodity.availability` and source policy in `config/data_sources.json`. Add a small exogenous-audit layer that evaluates source evidence independently from model code. Extend `research_dataset` manifests so admitted sources carry deterministic provenance without leaking metadata columns into model features.

## Task 1 — Deterministic admitted-source lineage
- [x] Add RED tests for source hash, availability/revision metadata, coverage and deterministic manifest identity.
- [x] Extend `PitFeatureSource`/dataset manifest with source-level lineage.
- [x] Keep availability metadata out of the feature matrix.
- [x] Run focused dataset tests GREEN.

## Task 2 — Family readiness audit
- [x] Add RED tests for `fit`, `fit-with-caveats`, and `not-fit` classifications.
- [x] Implement configuration-driven audit for storage/weather/power/positioning.
- [x] Require explicit blockers for non-admissible families and explicit caveats for conservative availability/coverage.
- [x] Run focused audit tests GREEN.

## Task 3 — Current preserved-evidence classification
- [x] Audit the preserved WNGSR, EIA-930, weather and CFTC state without inventing vintages.
- [x] Record recoverable public-archive paths separately from currently admissible evidence.
- [x] Produce `phase-b-evidence.json` with current verdicts and blockers.

## Task 4 — Verification and review
- [ ] Run full pytest, Ruff, `git diff --check`, and changed-file secret scan.
- [ ] Attempt independent review; manually review exact diff if configured backends remain unavailable.
- [ ] Commit exact reviewed Phase B tree. Publication/merge remains dependent on Phase A landing.
