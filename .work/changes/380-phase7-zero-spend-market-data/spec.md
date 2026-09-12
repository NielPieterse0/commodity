# Change Specification: Phase 7 Zero-Spend Market Data

- **Change ID**: `380-phase7-zero-spend-market-data`
- **Status**: Active
- **Complexity**: medium

## Outcome

Preserve the frozen Phase-7 market-source/execution contract while making current-gap acquisition quote-first and zero-spend by default, and establish Saxo as the eventual execution target without making Saxo a scientific source. Execution promotion is explicitly staged as paper -> Saxo SIM -> Saxo LIVE. LIVE may be inspected read-only before promotion to verify the real account, entitlements, instruments, and market-data visibility, but LIVE order submission remains the final stage only after paper and SIM evidence are complete.

## Authority and boundaries

- Programme authority: GitHub #361 Phase 7 and its landed prospective-serving contract.
- Frozen execution owner: `config/phase2_market_only.json`; Databento `ohlcv-1d` UTC-interval open remains authoritative.
- Canonical source owner: `config/data_sources.json#sources.databento_henry_hub`.
- Operator constraint: no new Databento credit may be spent without a prior quote and explicit later approval.
- Protected 2023+ confirmation outcomes remain unopened; this change performs no prospective decision or outcome backfill.

## Requirements

1. Databento automatic spending authority defaults to exactly `$0.00`; any billable fetch requires an explicit positive cost cap.
2. A metadata-only quote path reports cost and record counts for the exact Phase-7 partition triple: `definition`, `statistics`, `ohlcv-1d`.
3. Quote-only operations must never call `timeseries.get_range`.
4. Saxo LIVE uses a distinct LIVE endpoint and credential from SIM and exposes only read-only user, account, entitlement, reference-data and chart inspection.
5. LIVE readiness requires an active user, accepted OpenAPI market-data terms, `ContractFutures` legal access, a visible account, NYMEX entitlement, and successful NG plus MNG futures-space/chart resolution.
6. Saxo probes must not elevate session/trading capability, place orders, subscribe to paid data, or mutate the account.
7. A Saxo shadow observation may be written only after the corresponding Phase-7 decision is already persisted; it is stored in ignored local raw data, hash-chained, and bound to the exact Phase-7 decision hash.
8. Saxo remains non-canonical/shadow-only: it cannot drive Phase-7 decisions, fills, settlement or promotion evidence without a separate preregistered scientific amendment.
9. Execution promotion is ordered `paper -> saxo_sim -> saxo_live`; LIVE order submission is prohibited in this change and cannot be promoted ahead of completed paper and SIM evidence. Read-only LIVE verification does not constitute LIVE-trading promotion.

## Acceptance

1. Focused Databento/Saxo tests prove zero-spend defaults, GET-only LIVE inspection, sanitized identity handling, exact NG/MNG resolution, and canonical-ledger isolation.
2. The Phase-7 acquisition artifact records the observed local coverage boundary, metadata quote, zero billable requests, Saxo readiness requirements, and equivalence blockers.
3. The local Saxo shadow ledger is tamper-evident and cryptographically bound to an existing Phase-7 decision while remaining outside Git and outside scientific evidence.
4. Repository change-workflow scope and affected checks pass.
5. No scientific candidate, forecast, policy, risk, canonical fill, settlement, or evidence-classification rule changes.

## Risks and recovery

- Risk: treating Saxo chart bars as equivalent to Databento would silently change price aggregation/settlement semantics. Recovery: keep Saxo `canonical_market_source=false` and `backtest_evidence_allowed=false`.
- Risk: a future code path could spend residual Databento credit implicitly. Recovery: default cost authority is zero and billable retrieval requires an explicit positive override.
- Risk: LIVE account access may expose entitlements different from SaxoTrader display access. Recovery: inspect entitlements read-only before designing capture.

## Out of scope

- Databento data download or any other paid acquisition.
- Saxo OAuth refresh-token automation, subscriptions, or exchange-license purchase.
- Order submission of any kind in this data/readiness change. Paper execution testing and Saxo SIM order testing belong to the execution-adapter track; Saxo LIVE order submission is the final promotion stage after both are complete.
- Replacing Databento as the frozen Phase-7 canonical source.
- Creating or settling a prospective Phase-7 scientific evidence episode. A separate non-scientific Saxo execution-shadow observation is allowed only after its canonical decision already exists.
