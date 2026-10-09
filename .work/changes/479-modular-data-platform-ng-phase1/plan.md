# Modular Data Platform NG Phase 1 Implementation Plan

> Execute through the live KIS lifecycle; Issue #479 and WORK-479 remain requirements/command authority.

**Outcome:** Freeze the Commodity data-platform contract, then prove the smallest Natural Gas implementation without opening protected 2023+ outcomes.

**Source requirements:** GitHub issue #479, owner amendments through 2026-10-07, `AGENTS.md`, `config/quantitative_research_knowledge.json`, `config/data_sources.json`, and `config/research_dataset.json`.

## Global constraints

- Stay inside `scope.json`; preserve unrelated parallel development.
- `config/data_platform.json` is the single architecture owner; generated Markdown is projection only.
- Preserve existing operational source authority in `config/data_sources.json` and protected-evidence authority in `config/research_dataset.json`.
- Shared catalog and storage contracts must remain commodity-neutral; NG assumptions belong only in module/atlas records.
- Phase 1 infrastructure is PostgreSQL + Parquet/Zstd + DuckDB + Polars/Arrow, local-first and $0 incremental recurring spend.
- Do not enumerate, open, summarize, score, or otherwise inspect protected 2023+ outcome evidence.
- Optional future engines remain additive behind stable interfaces and are not Phase 1 dependencies.
## Task 1 — Freeze machine contracts

**Files:** `config/data_platform.json`, `contracts/data_platform.schema.json`, `contracts/raw_artifact_manifest.schema.json`, `tests/data/test_data_platform.py`.

- Define the two-plane architecture, generic identities, temporal clocks, natural-grain facts, source-vintage semantics, protected namespace, storage/layout rules, cost policy, migration triggers, and ownership/change rules.
- Add schema tests that reject NG-specific shared-core fields and prove a second commodity uses unchanged generic identities.
- Acceptance: both JSON contracts validate and Phase 1 contains no optional-engine dependency.

## Task 2 — Implement catalog, PIT view, and raw archive primitives

**Files:** `src/commodity/data_platform.py`, `src/commodity/raw_archive.py`, `tests/data/test_data_platform.py`, `tests/data/test_raw_archive.py`.

- Provide commodity-neutral PostgreSQL catalog DDL and validation helpers.
- Provide deterministic content identity and a causal AS-OF view builder with `available_at <= decision_time`.
- Provide SHA-256 raw-artifact registration, immutable identity checks, remote/restore verification, and protected-namespace separation.
- Acceptance: RED-GREEN tests cover generic catalog schema, PIT exclusion, sparse joins, hash mismatch, immutable re-acquisition, and protected archive isolation.

## Task 3 — Reconcile the NG Phase-1 atlas and durability ledger

**Files:** `data/manifests/ng-phase1-atlas.json`, `data/manifests/raw-artifacts.json`, `data/manifests/phase1-cost-ledger.json`.

- Reconcile all 42 known source families from the existing source library with an explicit implementation disposition without taking over operational source authority.
- Bind the known V2/V3 feature families and the PIT-ready MISO/CFTC evidence by reference.
- Inventory only non-protected raw working artifacts; record SHA-256, durability state, licensing class, and offsite/restore state.
- Acceptance: every known family has one disposition and no protected asset is enumerated in the development ledger.
## Task 4 — Prove analytical and PostgreSQL boundaries

**Files:** `scripts/data/benchmark_data_platform.py`, `scripts/data/verify_data_platform.py`, `data/manifests/phase1-benchmark.json`, `data/manifests/phase1-catalog-validation.json`.

- Benchmark representative synthetic NG-shaped Parquet scans, projection/filter pruning, windows, AS-OF joins, sparse joins, and constrained-memory execution without protected evidence.
- Validate the generic catalog against a disposable local PostgreSQL runtime when an already-available image/runtime permits it; otherwise record the bounded environment blocker rather than substituting SQLite.
- Record measured file/row-group evidence; tuning ranges remain guidance rather than schema.
- Acceptance: benchmark evidence is reproducible and verifier fails closed on contract, manifest, isolation, cost, or atlas violations.

## Task 5 — Register authority and generated documentation

**Files:** `AGENTS.md`, `.github/workflows/ci.yml`, `config/documentation_authority.json`, `config/documentation.json`, `config/rule_verification.json`, `scripts/verify.ps1`, `scripts/docs/generate_docs.py`, generated owned pages.

- Register `config/data_platform.json` as architecture owner and the data-platform verifier as pre-CI authority.
- Add a generated `docs/data-platform.md` projection and update the existing data manifest/rule verification projections.
- Acceptance: documentation generation/check is deterministic and Markdown does not become competing authority.

## Task 6 — Verify, review, and promote

- Run focused tests first, then `scripts/data/verify_data_platform.py`, documentation check, affected pytest, ruff, whitespace, and the repository change-workflow check.
- Run KIS architecture/documentation/code review on the exact worktree, fix blocking findings, and rerun affected evidence.
- Commit through the governed workflow, prepare the reviewable PR, require exact-head GitHub Actions, then merge/reconcile/clean through KIS.
