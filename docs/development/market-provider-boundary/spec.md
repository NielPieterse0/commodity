# Canonical Market Provider Boundary and Subscription Value Spec

**Development level:** Complex
**Date:** 2026-08-13

## Outcome

Keep canonical futures research provider-neutral while continuing to evaluate Massive as a replaceable data source. A future decision not to use Massive must not require changes to core CLI or market-domain logic.

## Requirements

- **R1 — Provider-neutral core:** `commodity.cli` and canonical market-domain code must not import or name a concrete market-data vendor.
- **R2 — Lazy adapter loading:** The canonical source configured in `config/data_sources.json` is resolved to a provider adapter by convention at runtime. Missing adapters fail with a bounded provider-loading error.
- **R3 — Narrow interface:** A canonical futures provider exposes only `fetch_contract_history(...)` and `capture_archive(...)`; provider authentication, pacing, pagination, and wire formats remain inside the adapter.
- **R4 — Rank-bounded preservation:** V1 curve preservation means expiry-ranked M1-M12 per trading date, not one absolute expiration cutoff across the whole capture period.
- **R5 — Fail closed:** Incomplete metadata, invalid rank-window inputs, snapshot tampering, pagination truncation, and provider failures continue to fail closed.
- **R6 — No licensing promotion:** Massive remains non-canonical for backtest evidence until rights are independently verified. This slice does not alter trading authority.
- **R7 — Reversible provider footprint:** New Massive-specific runtime code lives in one adapter module. Provider-specific configuration, credentials, tests, and historical documentation remain identifiable for later removal.
- **R8 — Evidence-only subscription evaluation:** Preserve no new licensed market values in Git. Commit only deterministic aggregate findings and source hashes from the ignored local snapshot.

## Current evidence

The preserved 2024-08-14 through 2026-08-12 archive contains 500 sessions and 11,200 canonical rows. Expected M1-M12 coverage is 5,988 / 6,000 cells (99.8%), but 5,209 rows (46.51%) are outside M12 because the existing capture uses a single end-date-plus-12-month expiry cutoff rather than per-session ranks.

On the M1-M12 panel, settlement differs from session close on 5,840 / 5,988 rows (97.53%). The simple leakage-safe next-session screen found no return/direction advantage from the richer curve features; absolute-return prediction showed only a small, statistically uncertain improvement over price-only features. The paid-plan question is therefore history depth and regime coverage, not feature count.

## Boundaries

- No serious model training or strategy optimization.
- No live trading or execution changes.
- No new external dependencies.
- Do not redistribute Massive raw values or snapshot contents.
- Existing immutable historical development records are not rewritten merely to erase past provider evaluation; current runtime and authoritative documentation are the removal boundary.
