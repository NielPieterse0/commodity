# Databento vs Massive Futures Evaluation Specification

**Development level:** Complex
**Status:** approved for implementation
**Approval basis:** User approved the Databento-vs-Massive slice after PR #10 landed.

## Outcome

Add Databento as a removable canonical-futures provider adapter and produce bounded evidence comparing it with the existing Massive adapter for CME Henry Hub NG research, without changing canonical-provider selection or evidence/licensing authority prematurely.

## Requirements and invariants

- **R1 — Provider isolation.** Databento runtime code must implement the existing `CanonicalFuturesProvider` boundary. Removing Databento later must not require edits to `commodity.cli` or provider-neutral market-domain code.
- **R2 — Secret handling.** Authentication uses `DATABENTO_API_KEY`; the value must never be logged, committed, copied into a worktree file, manifest, review artifact, or exception message. `.env.example` contains only the empty variable name.
- **R3 — Metadata-first entitlement probe.** Before downloading billable time-series data, probe free metadata for dataset/schema availability, entitled date ranges, request cost, and record counts. Any billable request must be explicitly bounded and justified by the metadata result.
- **R4 — Canonical semantics.** The adapter must preserve raw contract identity, expiration, trading/reference date, official settlement, and available historical volume. It must fail closed when required settlement or expiration semantics cannot be established.
- **R5 — Point-in-time statistics.** CME settlement rows come from Databento `statistics` records and use the exchange trading reference date. When multiple settlement messages exist for one session, final settlement is preferred. Preliminary/final state and source publication timestamps remain available as provenance rather than being silently discarded.
- **R6 — Bounded benchmark.** Compare Databento with the preserved Massive evidence using a small reproducible NG sample before any meaningful download. Record history depth, field coverage, contract coverage, settlement/volume semantics, estimated cost, and operational constraints. Licensed market values remain ignored and out of Git.
- **R7 — No premature promotion.** `market_canonical.provider` remains `massive_futures` unless a separate explicit decision changes it. Massive licensing remains blocked; Databento licensing/backtesting rights must also be treated as unresolved until verified. No canonical-evidence or LIVE-execution authority is changed.
- **R8 — Current-main reconciliation.** The final PR must be reconciled onto the current remote `main` so PR #9/#10 history is preserved and the PR diff contains only this Databento slice.
- **R9 — Verification.** Tests cover authentication redaction, HTTP request shape, metadata probing, statistic normalization, final-settlement selection, fail-closed behavior, provider factory compatibility, and no core provider coupling. Full repository tests, Ruff, whitespace, secret scan, code review, modularity review, and exact-head CI are required.

## Boundaries

- Databento historical API calls are external authenticated operations. Local Work may not bypass its outbound-network restriction.
- The adapter uses the documented Databento HTTP API through the existing `requests` dependency; no Databento SDK dependency is required.
- Dataset target is `GLBX.MDP3`, parent product `NG`, with `statistics` and `definition` as core schemas.
- Raw Databento market values and any billable response artifacts remain under ignored snapshot/evidence locations.
- Current Massive archive and provider behavior remain intact.

## Explicit exclusions

- No switch of the canonical provider in this slice.
- No serious model training, strategy tuning, or performance claim from the provider comparison.
- No live data subscription, order routing, or LIVE trading changes.
- No redistribution-rights assumption from technical API access.
- No large Databento download without a successful metadata/cost probe first.

## Architecture and data flow

`provider evaluation metadata -> DatabentoFuturesClient -> DatabentoFuturesProvider -> CanonicalFuturesProvider -> existing canonical validation/term-structure code`

The client owns Databento HTTP/auth/error semantics. The provider adapter owns Databento-to-canonical normalization and archive/probe orchestration. Provider-neutral core code remains unchanged.

## Security, failure, migration, and reversibility risks

- Credential leakage is blocking and requires immediate removal/rotation if detected.
- HTTP 401/402/403 responses are entitlement/account evidence, not retryable success states.
- Databento API v0 is pre-stable; endpoint details stay isolated in the adapter.
- Final-settlement selection must not confuse preliminary statistics with final values.
- Removal is a normal revert/delete of the Databento adapter/tests/docs/config entry; Massive remains configured throughout.

## Acceptance and release evidence

- Targeted Databento/provider tests pass after observed RED failures.
- Metadata probe is either executed through an approved authenticated connector or explicitly recorded as blocked by the runtime network boundary; no entitlement result is fabricated.
- Public-source capability evidence is recorded separately from account-specific entitlement evidence.
- Full pytest, Ruff, whitespace, and secret-pattern checks pass on the exact local commit.
- Code-quality and architecture/modularity reviews have no unresolved blocking findings.
- Final PR is open, non-draft, based on current remote `main`, and exact-head CI passes.

## Rollback/recovery

Revert the Databento PR. No persistent database migration, canonical-provider switch, execution-policy change, or committed licensed dataset is introduced.

## Open decisions

- **Account entitlement evidence:** owner = user/project. Record the live result if an approved connector can use the existing key; otherwise retain an explicit external execution gate.
- **Future provider selection:** owner = user/project. Out of scope for this slice; benchmark evidence informs a later explicit decision.

## Specification review approval

Approved by the user in the continuation request authorizing the Databento-vs-Massive benchmark slice after PR #10 merge.
