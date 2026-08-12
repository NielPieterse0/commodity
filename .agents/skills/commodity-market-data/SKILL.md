---
name: commodity-market-data
description: Use when acquiring, validating, joining, or versioning Commodity natural-gas market/fundamental data where historical availability, release timing, revisions, futures contracts, rolls, sessions, and term structure must be point-in-time correct.
---
# Commodity Market Data

## Purpose
Extend the shared `data-engineer` and `dataset-auditor` disciplines with Commodity-specific point-in-time market-data rules.

## Required Rules
1. Store observation time separately from publication/release time and ingestion time.
2. Preserve the vintage/revision identity actually available at each forecast decision point; never substitute later revisions silently.
3. Weather inputs must identify forecast issue/vintage time; subsequently observed weather is not a historical forecast feature.
4. Fundamental releases such as storage or positioning must respect their actual publication timestamp and lag.
5. Futures data must preserve contract identity, expiration, session/calendar, timezone, and source-native timestamps.
6. Continuous contracts must record roll rule, adjustment method, roll dates, and source contracts; never treat a synthetic series as an exchange-traded instrument.
7. Term-structure features may use only contracts and quotes available at the information cutoff.
8. Every derived dataset must carry immutable source identities, hashes, as-of timestamp, vintage identity, and transformation lineage required by `../../../contracts/experiment.schema.json`.

## Boundary
Own point-in-time data correctness and futures-data semantics. Do not own feature selection, model fitting, trading policy, position sizing, broker logic, or LIVE authorization.

## Completion
A dataset is usable only when a reviewer can reconstruct what information was available, from which contract/vintage, at the stated forecast cutoff.
