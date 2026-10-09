# Change Specification: Modular Data Platform NG Phase 1

- **Change ID:** `479-modular-data-platform-ng-phase1`
- **Status:** Active implementation
- **Complexity:** large
- **Risk triggers:** architecture_boundary, external_action, migration, money, persistent_state, public_contract, sensitive_data

## Outcome

Implement Issue #479 Phase 0/1 as a commodity-neutral data-platform foundation plus the first bounded Natural Gas module, without opening protected 2023+ outcomes.

## Authority and scope

- Requirements authority: GitHub issue #479 and owner amendments through 2026-10-07.
- Repository authority: `AGENTS.md`.
- Data-engineering/PIT guidance: `config/quantitative_research_knowledge.json`.
- Operational source status owner: `config/data_sources.json`.
- Research/protected-evidence timing owner: `config/research_dataset.json`.
- Owned/shared/excluded paths and base identity: `scope.json`.
## Binding requirements

1. `config/data_platform.json` MUST be the machine-readable architecture owner and MUST validate against `contracts/data_platform.schema.json`.
2. Phase 1 MUST use PostgreSQL for control/catalog state and Parquet/Zstd + DuckDB + Polars/Arrow for bulk analytical history/pipelines.
3. Shared identities and catalog schema MUST be commodity-neutral; NG-specific values MUST live in NG module/atlas records.
4. Source/event/publication/availability/ingestion/outcome clocks and economic/source vintages MUST remain explicit and distinct from database snapshot history.
5. Causal views MUST exclude records with `available_at > decision_time`; sparse families MUST NOT delete otherwise valid session rows.
6. Raw evidence MUST be byte-identified by SHA-256, immutable by identity, recoverable from an off-machine archive when licensing permits, and independently verifiable after restore.
7. Development and protected-confirmation archives MUST use separate namespaces/credentials; normal development MUST NOT enumerate protected assets.
8. Phase 1 incremental recurring infrastructure spend MUST target $0. Paid/managed upgrades require explicit operator approval.
9. All 42 known NG/global/Norway source families MUST have an implementation disposition without redefining `config/data_sources.json` operational authority.
10. Optional DuckLake/Iceberg/TimescaleDB/ClickHouse/streaming/managed services MUST NOT be Phase 1 dependencies.
## Acceptance evidence

- JSON Schema validation for architecture and raw-artifact manifests.
- Contract test proving a second commodity can add instruments, units, locations, calendars, and source families with no shared-core schema change.
- PIT tests for decision-time exclusion, explicit revisions, and sparse left/as-of joins.
- Raw archive tests for SHA-256 identity, collision/re-acquisition behavior, remote verification, restore verification, and protected namespace separation.
- NG atlas coverage test: 16 US + 15 global/interconnect + 11 Norway/Europe = 42 families, each with an allowed disposition.
- Representative DuckDB/Parquet benchmark evidence using non-protected synthetic/development data only.
- PostgreSQL catalog validation evidence or an explicit environment blocker; SQLite is not an acceptable substitute.
- Cost ledger with actual incremental recurring spend, target $0.
- Generated documentation and rule-verification checks.
- KIS exact-worktree review and repository verification before promotion.

## Risks and recovery

- **Architecture drift:** schema validation and single-owner authority prevent Markdown/config divergence.
- **PIT leakage:** fail-closed timestamp contract plus protected namespace policy.
- **Raw loss:** manifest-bound offsite identity, integrity checks, and restore verification.
- **Provider lock-in:** portable hash/object identity and stable interfaces.
- **Parallel-change conflict:** retain bounded owned paths and validate claims before commit.
- **Recovery:** revert the governed change commit; immutable raw/source evidence is never destructively migrated by this issue.

## Out of scope

- Opening or evaluating protected 2023+ outcomes.
- Migrating all historical observations into PostgreSQL.
- Deploying managed/cloud databases, streaming, ClickHouse, TimescaleDB, Iceberg, or DuckLake.
- Purchasing new datasets or recurring infrastructure without explicit operator approval.
