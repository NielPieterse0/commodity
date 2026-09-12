# Phase 7 Zero-Spend Market Data Implementation Plan

**Goal:** Preserve the frozen Databento scientific contract, prevent unapproved Databento spend, and establish Saxo as the eventual execution target under the ordered promotion path paper -> Saxo SIM -> Saxo LIVE. LIVE access in this change is read-only shadow/readiness inspection only and does not promote trading authority.

## Constraints

- Databento remains the Phase-7 canonical scientific and settlement source.
- Automatic Databento spend authority remains exactly `$0.00`.
- Execution promotion is paper first, then Saxo SIM, then Saxo LIVE; LIVE order submission is not eligible in this change.
- Saxo LIVE access is GET-only; no order, session-capability, subscription, or account mutation is implemented.
- Secrets remain runtime-only and are never persisted in repository evidence.
- Saxo shadow observations are broker-execution diagnostics only and cannot create, alter, or settle Phase-7 scientific evidence.

## Work

1. Keep exact metadata quote-before-spend controls for the Databento `definition`, `statistics`, and `ohlcv-1d` partition triple.
2. Verify Saxo LIVE user state, OpenAPI market-data terms, NYMEX entitlement, visible account, and actual NG/MNG contract/chart access.
3. Record only sanitized LIVE readiness evidence; never retain user/account/client identifiers or tokens.
4. Bind broker-native Saxo observations to an already-persisted Phase-7 decision using its exact record hash.
5. Store Saxo market observations only in the ignored local raw-data tree with a tamper-evident SHA-256 chain.
6. Generate affected documentation and run focused/governed verification once for the exact integrated tree.
7. Land through KIS/GitHub without spending Databento credit or requiring LIVE trading authority.
