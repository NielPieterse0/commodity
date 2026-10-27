# Phase 2 Market Truth Implementation Plan

**Goal:** Deliver #482 in the independent `change/482-data-phase2-market-truth` worktree without reading protected 2023+ outcomes.

**Authorities:** AGENTS.md; issue #482; config/data_platform.json; config/data_sources.json; config/research_dataset.json; contracts/*.schema.json.

**Design:** Instrument-neutral Python normalization, NG-specific bounded vendor adapter, deterministic time-aware 12-rank curve, sparse features, causal as-of snapshot, explicit Parquet/ZSTD publisher with hashed provenance. The current eager in-memory path is not approved for historical volume. Inputs are explicit allow-listed, verified files; never scan a raw archive.

**Scope:** Newly isolated `src/commodity/market_truth/**`, bounded tests, CLI, and owned contracts/config/manifests. Existing provider transforms are read-only references.

**Steps:**
- [x] Claim WORK-482, refresh default ref, create governed independent worktree.
- [x] Read KIS/data-engineering/development/verification/security skills and inspect source contracts.
- [x] Implement initial versioned definitions, statistics, OHLCV and causal contract mapping with synthetic validation.
- [x] Implement initial 12-rank curve, derived market features and causally filtered V3 snapshot API.
- [x] Implement initial deterministic Parquet build and manifest with protected boundary.
- [ ] Add negative/temporal/coverage/rebuild/parity/performance tests.
- [ ] Execute focused and canonical verification; close review findings.
- [ ] Obtain licensed development-only source inventory, run historical build and archive check; diagnose blocked gates.
- [ ] Use governed publication/PR/CI/merge/cleanup when all prerequisites pass.
