# V1 PIT Dataset + Model Tournament Specification

**Program issue:** `NielPieterse0/commodity#13`

## Objective

Move Commodity from provider/data plumbing into empirical research by producing the first deterministic leakage-safe research dataset and a reproducible walk-forward baseline tournament.

## Boundaries

- U.S. / Henry Hub remains the active forecast target.
- Massive and Databento remain replaceable provider adapters; this slice does not choose a winner.
- `canonical`, `research_pit`, and `screening` retain their existing meanings from `config/data_sources.json` and `src/commodity/availability.py`.
- Screening-only revised histories must never be accepted into a `research_pit` tournament.
- Europe/Norway/global inputs and Kronos remain later incremental layers.
- No trading or execution permission changes.

## Dataset design

The dataset builder produces a daily supervised frame at the existing prediction cutoff: after the current completed daily market bar, forecasting the next completed daily bar.

The base frame contains deterministic market/seasonal features plus the next-session return target. Optional exogenous frames are joined only through `asof_join_point_in_time`, using each row's `available_at` and admissibility metadata.

The builder accepts only `research_pit` or `canonical` evidence for tournament datasets. `screening` is rejected rather than silently downgraded.

A dataset manifest records a stable content hash, row/column counts, time coverage, target, prediction semantics, evidence mode, included source families, and material exclusions.

## Completeness semantics

`pit_core` means the dataset is internally leakage-safe for the sources actually included. It does **not** mean every desired U.S. V1 family is present.

`full_v1` may be claimed only when every family configured as required for the active experiment is present and PIT-admissible. Missing or screening-only families are reported as exclusions and make the completeness check fail closed.

For the current repository state, market/calendar features form the executable PIT core. Revision-bearing EIA history remains excluded; eligible issued-weather history can be added when sufficient vintages are available.

## Tournament design

The tournament uses chronological expanding walk-forward evaluation only. Random/shuffled row splits are not exposed.

The first ladder is:

1. zero-return naive baseline;
2. Ridge linear/statistical baseline;
3. histogram gradient boosting challenger using only the same frozen dataset and split protocol.

Every model produces predictions and forecast-only metrics. Tournament ranking uses the configured primary metric; downstream signal/backtest execution remains separate.

## Acceptance

- deterministic dataset identity for identical inputs;
- explicit rejection of screening evidence;
- optional PIT exogenous joins never use future information;
- chronological walk-forward split validation;
- common-protocol tournament across enabled baseline implementations;
- dataset/tournament artifacts are reproducible and local/ignored;
- focused tests, full pytest, Ruff, review, PR, merge, and cleanup pass.