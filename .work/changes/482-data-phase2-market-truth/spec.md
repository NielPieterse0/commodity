# Phase 2 Implementation Contract

Authority: GitHub issue #482, parent #481, implemented Phase 1 #479, AGENTS.md, config/data_platform.json, config/data_sources.json, config/research_dataset.json and contracts/data_platform.schema.json.

Outcome: reproducible, immutable Henry Hub NG natural-grain contract-definition, daily OHLCV, exchange statistics, causal M1–M12 ranks and V3-readable as-of features, with lineage and validation.

Boundaries: no paid acquisition, no fundamental joins, no protected 2023+ source opening or enumeration, no synthetic continuous authority, no silent missingness fill, no catalog bulk ingestion. Supabase remains the existing control catalog. New output is private research only; no redistribution.

Acceptance: one-to-one grain, temporal revision/duplicate validation, deterministic curve ranks, missing ranks and unavailable values visible, strict decision_time >= available_at, no cross-roll price momentum, hashed inputs/outputs and verification report, synthetic future-invariance tests, reproducible compressed Parquet where the approved runtime is available. Real-source build requires separately confirmed development-only input provenance and source-coverage evidence; if absent status remains blocked, not passing.
