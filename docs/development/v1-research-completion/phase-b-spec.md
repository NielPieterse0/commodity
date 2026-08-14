# V1 Research Completion — Phase B Specification

Program: GitHub issue #15. Phase B: #18. Baseline: reviewed Phase A source commit `2b301e589af9a5ee50e448e7b2d248ddfa40fe9c`.

## Goal
Make the four required U.S. exogenous families — storage, weather, power, and positioning — independently auditable for point-in-time research admission. A family is either admitted with deterministic availability/revision lineage or blocked explicitly; no family may appear complete because a current revised history merely exists.

## Requirements
- **R1 — family audit contract:** Every required exogenous family receives one verdict: `fit`, `fit-with-caveats`, or `not-fit`, plus source, evidence mode, availability/revision status, coverage, deterministic source hash, and blockers/caveats.
- **R2 — admitted-source lineage:** Every `PitFeatureSource` admitted to a dataset records deterministic input identity and the availability/revision metadata actually used by the as-of join.
- **R3 — storage:** Current WNGSR history remains non-admissible for `research_pit` while original/revision vintages are incomplete. Release-time reconstruction alone cannot override revision leakage.
- **R4 — power:** Current EIA-930 history remains non-admissible for `research_pit` while historical submission/revision vintages are unresolved.
- **R5 — weather:** Immutable issued model runs may enter `research_pit` using source availability when verified or the configured conservative model-delivery bound. Full-V1 readiness additionally requires material coverage across the research window.
- **R6 — positioning:** CFTC values may enter only when an immutable/as-published value source and a conservative release-time rule cover the relevant report. Missing historical release evidence or value-vintage ambiguity fails closed.
- **R7 — completeness:** `full_v1` cannot be claimed from family names alone; required families must have admissible, non-empty coverage at the retained prediction cutoffs.
- **R8 — authority boundaries:** Source timing/revision policy remains owned by `config/data_sources.json`; required families remain owned by `config/experiment.json`; no LIVE or market-license gate changes.

## Acceptance evidence
- Tests prove source lineage is deterministic and metadata survives dataset construction without becoming model features.
- Tests prove revised storage/power sources and unresolved positioning evidence are `not-fit`/rejected from `research_pit`.
- Tests prove immutable issued weather is admissible with conservative timing but coverage can still block full-V1 readiness.
- A Phase B evidence artifact classifies all four families from the currently preserved source state.
- Full pytest, Ruff, whitespace and secret-pattern gates pass; review has no blocking/important finding.
