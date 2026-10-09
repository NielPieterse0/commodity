# Tasks: Modular Data Platform NG Phase 1

- [x] Confirm live KIS authority, classification, scope, base SHA, and claim WORK-479.
- [x] Load KIS, develop-code, data-engineering, documentation, planning, and TDD procedures.
- [x] Map Issue #479 requirements into the bounded governed plan/spec.
- [x] RED: add contract tests for architecture neutrality, temporal/PIT behavior, atlas coverage, raw integrity, and protected isolation.
- [x] GREEN: implement `config/data_platform.json` and both JSON Schemas.
- [x] GREEN: implement commodity-neutral catalog/PIT helpers and raw-archive primitives.
- [x] Build the 42-family NG Phase-1 atlas, raw-artifact ledger, and $0 cost ledger.
- [x] Add deterministic data-platform verifier and representative DuckDB/Parquet benchmark evidence.
- [x] Repair the worktree Python environment to the repository lock; replace drifted scikit-learn 1.9.1 with locked 1.9.0 and restore the complete locked dependency set without weakening Windows Application Control.
- [x] Pin the Phase-1 DuckDB/Polars/psycopg dependencies and add the provider-neutral boto3 S3-compatible raw archive adapter with remote byte re-hashing and restore verification.
- [x] Recover the representative pre-protected raw artifact from existing project-local evidence and verify its manifest SHA-256 exactly.
- [x] Validate the PostgreSQL catalog on the dedicated $0/month Supabase Phase-1 project: 17-table generic catalog deployed in private `commodity_control` schema, transactional JSONB/FK/temporal probe passed and rolled back, security advisor clean, and FK indexes added from advisor feedback.
- [x] Register architecture/documentation/rule-verification authority and regenerate owned documentation.
- [x] Complete representative off-machine upload, independent remote SHA-256 verification, and local-loss restore drill against the private Supabase S3-compatible development bucket.
- [x] Final strict data-platform verification is green (archive 7/7; `--require-durable-raw --require-postgres` passed) and exact-commit specialist review is closed through the KIS-declared `manual_fallback=exact-diff`; use exact-head provider CI for the full suite because local Windows Application Control currently blocks DuckDB's native DLL.
- [ ] Commit through KIS and project the change classification to WORK-479.
- [ ] Prepare reviewable PR, require exact-head Actions, merge/reconcile Work/documentation, and clean worktree through KIS.
