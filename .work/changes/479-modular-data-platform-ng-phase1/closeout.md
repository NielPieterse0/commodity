# Closeout: Modular Data Platform NG Phase 1

## Implemented scope

- Froze the commodity-neutral Phase-1 data-platform contract at `config/data_platform.json`: PostgreSQL control/catalog plane plus Parquet/Zstd, DuckDB, and Polars/Arrow analytical plane.
- Added generic PostgreSQL catalog DDL with covering foreign-key indexes, strict causal AS-OF/PIT helpers, explicit source-vintage semantics, and deterministic same-availability tie handling; deployed and validated the 17-table catalog in the dedicated Supabase `commodity_control` schema.
- Added raw-artifact SHA-256 identity, immutable source/content identity checks, offsite verification records, restore verification, and development/protected archive separation controls.
- Reconciled all 42 Natural Gas/global/Norway source families, versioned existing feature families, recorded the $0 recurring-cost ledger, and produced representative synthetic DuckDB/Parquet benchmark evidence.
- Registered the architecture owner, generated documentation, pre-CI/CI data-platform verifier, and protected-confirmation boundary without opening or enumerating protected 2023+ outcomes.

## Implementation evidence

- Source base: `f5ff94128811efca8d196bb583af228f5d7bf977`; final implementation commit/tree is recorded by the governed Git step.
- Focused verification: `tests/data/test_data_platform.py tests/data/test_raw_archive.py` = 19 passed; `scripts/data/verify_data_platform.py` passed.
- The worktree environment was repaired to the repository lock, including replacement of drifted scikit-learn 1.9.1 with locked 1.9.0; the Windows Application Control failure no longer reproduces.
- A full canonical `scripts/verify.ps1` run before the final Supabase archive/environment-adapter delta was green at 1,228 passed, 12 skipped, with one pre-existing MISO fixture warning. After the final delta, the strict data-platform gate passes with both `--require-durable-raw` and `--require-postgres`, and raw-archive tests are 7/7 green; a fresh full local rerun is currently blocked only by Windows Application Control rejecting DuckDB's native `_duckdb` DLL.
- Supabase PostgreSQL validation passed in project `qbugfnuzjbmdtgrqznxw` (`eu-central-1`): 17 tables in private `commodity_control` schema, transactional JSONB/FK/temporal probe passed and rolled back, security advisor returned zero findings, and the initial unindexed-FK advisor findings were resolved with covering indexes.
- Benchmark: 1,500,000 synthetic NG-shaped rows, Parquet/Zstd, 85,249,533-byte file, 6 row groups, projection/filter pruning, window, AS-OF, sparse join, and >4x input-to-memory constrained scan.
- Review closure: exact-commit specialist review attempts were bound to `852d50bc9e1c347c4a09e1c3e13fe5466eb53919`. Code-quality, architecture, and documentation projectors declared `manual_fallback=exact-diff` because the 38-file change exceeded bounded projector coverage; safety/security and test-quality routes also declared exact-diff fallback after configured NVIDIA reviewer outputs were unusable. The required manual exact-diff review covered source, tests, contracts, Supabase catalog/archive evidence, environment examples, and protected-data boundaries and found no blocking implementation or security issue. `.env` remains local/ignored and secrets are not committed.
- PromotionReady / reusable evidence: pending governed commit/lifecycle derivation after final verification.

## Provider and landing evidence

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending and required as the exact-head provider gate because the current workstation policy blocks DuckDB's native runtime.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: pending.
- Cleanup: pending.

## Research return, when applicable

- Upstream L3 authority: Issue #479 Phase 0/1 requirements and owner amendments through 2026-10-07.
- Exact implementation/landing identity returned to research lineage: pending landing.
- Scientific escape/re-entry: none; implementation preserved the agreed architecture/PIT/protected-data contract.

## Residual items

- PostgreSQL server execution validation is complete on the dedicated $0/month Supabase project. The catalog remains isolated from the public Data API in the private `commodity_control` schema.
- Raw off-machine durability is proven for the representative development artifact. `ng_f_daily.csv` (447,149 bytes; SHA-256 `5fc38277e39dd644dfa0ac1f06621c5a1f7966824c92c536739e29b043e2ab1b`) was uploaded to private Supabase bucket `commodity-raw-development`, independently re-hashed from remote bytes, then restored after moving the local source out of its normal path; the restored bytes matched the same SHA-256 and the manifest records `durably_acquired` / `restore.status=verified`.
- Historical MISO and weather raw archives referenced by source authority are not present in this checkout and must be located or reacquired before they can be declared durable.
- Protected confirmation data was not opened, inspected, enumerated, benchmarked, or included in the development manifest.
- Current local execution blocker: Windows Application Control rejects DuckDB's native `_duckdb` DLL. No security-policy bypass is used; exact-head provider CI is required to supply the final native-runtime full-suite evidence if the local policy continues to block DuckDB.
