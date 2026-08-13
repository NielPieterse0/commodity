# U.S. V1 Point-in-Time Availability Specification

**Development level:** Medium  
**Status:** approved for implementation

## Outcome

Add an explicit, leakage-aware availability layer for preserved U.S. V1 exogenous data so exploratory research can use justified source timing without silently promoting current-state historical snapshots to canonical point-in-time evidence.

## Requirements

- **R1 — Availability contract.** Every derived exogenous row used in a time-ordered experiment must distinguish `observed_for`, `available_at`, `availability_status`, and `revision_status`. Unknown availability remains unresolved rather than inferred implicitly.
- **R2 — EIA-930 timing.** Reconstruct conservative research availability from EIA's published operating-data schedule: hourly demand after the completed hour, day-ahead demand forecast by the published morning cutoff, and prior-day generation by the published morning cutoff. Current historical API snapshots remain explicitly revision-bearing and noncanonical.
- **R3 — WNGSR timing.** Encode the regular Thursday 10:30 America/New_York release rule and official holiday exceptions only where the exception registry is covered. A reconstructed release timestamp must not by itself make a current historical storage snapshot point-in-time safe; published revisions/vintages remain a separate gate.
- **R4 — Issued weather timing.** Preserve source `issued_at` separately from availability. For research screening, support a conservative Open-Meteo/ECMWF availability timestamp derived from documented global-model delivery lag plus the documented server-consistency safety margin. This reconstruction is never canonical historical availability.
- **R5 — Evidence modes.** Support three explicit modes: `canonical`, `research_pit`, and `screening`. `canonical` accepts only verified point-in-time rows; `research_pit` may accept conservative timing when revision history is point-in-time safe; `screening` may admit current revised histories only when labelled noncanonical with revision-leakage risk.
- **R6 — As-of joins.** Point-in-time joins must never use rows whose selected availability timestamp is later than the prediction cutoff. Unresolved rows must fail closed in `canonical` and `research_pit` modes.
- **R7 — Configuration ownership.** Source timing rules and exception coverage belong in `config/data_sources.json`; runtime code consumes configuration rather than hard-coding provider policy.
- **R8 — No market-license promotion.** Massive licensing, redistribution, and canonical market-evidence gates remain unchanged.

## Boundaries and exclusions

- No serious model training or research-stage promotion in this slice.
- No change to LIVE execution policy.
- No claim that EIA current-state history reproduces every originally published historical value.
- No claim that historical Open-Meteo model initialization time equals exact API availability time.
- Monthly EIA Natural Gas production/consumption/trade/spot vintage reconstruction remains unresolved unless independently evidenced during implementation.

## Acceptance evidence

- Tests cover DST-aware timestamps, EIA-930 field-specific lags, WNGSR holiday overrides, weather conservative timing, evidence-mode rejection/acceptance, and future-information exclusion in as-of joins.
- `config/data_sources.json` records authoritative timing rules and residual vintage limitations.
- README/data-manifest current-state text is reconciled with the implemented evidence tiers.
- Full pytest, Ruff, and whitespace checks pass on the PR head.

## Authoritative source basis

- EIA Hourly Electric Grid Monitor documents demand, demand-forecast, and generation availability schedules and revision behavior.
- EIA WNGSR documents Thursday 10:30 Eastern releases, holiday exceptions, and historical revision policy.
- Open-Meteo Single Runs documents that model initialization is not public availability; global models generally require 4–6 hours, and the model-updates documentation recommends an additional 10-minute consistency margin.
