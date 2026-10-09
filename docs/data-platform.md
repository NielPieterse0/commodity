<!-- GENERATED FILE. DO NOT EDIT. Source: config/data_platform.json, contracts/data_platform.schema.json, contracts/raw_artifact_manifest.schema.json, data/manifests/ng-phase1-atlas.json, data/manifests/ng-phase1-feature-registry.json, data/manifests/phase1-benchmark.json, data/manifests/phase1-cost-ledger.json, data/manifests/phase1-catalog-validation.json, data/manifests/raw-artifacts.json -->

# Commodity Data Platform

Source authority: `config/data_platform.json`. This page is generated and is not a competing architecture owner.

## Phase 1 boundary

- Required stack: `postgresql`, `parquet_zstd`, `duckdb`, `polars_arrow`.
- Scope: `natural_gas_only_with_commodity_neutral_shared_core`.
- Incremental recurring infrastructure target: **$0**.
- Bulk analytical observations remain Parquet/Zstd; PostgreSQL is the small identity/lineage/quality/catalog plane.
- Optional DuckLake, TimescaleDB, ClickHouse, Iceberg, streaming, catalogs, and remote services remain deferred until measured need.

## Point-in-time contract

- Causal rule: `available_at <= decision_time`.
- Source/economic vintages and revisions are explicit and are not database-snapshot substitutes.
- Sparse families stay sparse; experiment-specific wide matrices are reproducible projections.
- Protected-confirmation evidence is isolated by namespace and credential, and development may not enumerate it.

## Natural Gas Phase 1

- Reconciled source families: **42** (16 U.S./Henry Hub, 15 global/interconnect, 11 Norway/Europe).
- Versioned existing feature families: `technical`, `volatility_tail`, `market_structure_positioning`.
- BHLR real-time/vintage predictor audit: `LIT-BHLR-RTDB`, development PIT eligible through 2022-12-31; outcome member excluded.

## Measured local evidence

- Benchmark: 1,500,000 synthetic NG-shaped rows, 85,249,533 Parquet bytes, 6 row groups.
- Constrained-memory ratio: 4.07x input file / configured DuckDB memory.
- PostgreSQL catalog static validation: `passed`; server validation: `passed`.
- Raw archive namespace: `operational`; representative byte durability remains governed by the raw-artifact manifest.
- Actual incremental recurring infrastructure spend: **$0 / month**.

## Canonical evidence

- Architecture: `config/data_platform.json`.
- Raw byte identity/durability: `data/manifests/raw-artifacts.json`.
- NG family disposition: `data/manifests/ng-phase1-atlas.json`.
- Existing feature versions: `data/manifests/ng-phase1-feature-registry.json`.
- Performance/layout evidence: `data/manifests/phase1-benchmark.json`.
- Cost evidence: `data/manifests/phase1-cost-ledger.json`.
- PostgreSQL validation evidence: `data/manifests/phase1-catalog-validation.json`.
