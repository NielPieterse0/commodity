# Canonical Roll Policy and History Validation Specification

**Status:** implemented and merged via PR #3 on 2026-08-12; canonical backtest evidence remains licensing-blocked
**Development level:** Complex

## Outcome

Close as much of the canonical-market evidence gate as the verified Massive account, deterministic roll methodology, licensing boundary, and reproducible evidence allow. Do not begin serious model training in this slice.

## Requirements

- **R1 — Synced isolation:** Development starts from GitHub `main` at `dc344c0` in a dedicated `.work/` worktree and feature branch, without modifying another agent's worktree.
- **R2 — Live account validation:** Probe the existing `MASSIVE_API_KEY` without exposing it. Record actual NG contract metadata depth, aggregate settlement/OHLCV depth, pagination, missing-session behavior, and available fields.
- **R3 — Safe authentication:** Massive authentication MUST use the supported Authorization header so request/HTTP error URLs do not contain the API key.
- **R4 — Canonical raw ownership:** Massive per-contract rows remain canonical; continuous series remain derived-only.
- **R5 — Deterministic roll policy:** Replace the canonical dependency on historical open interest with a prior-session volume + calendar-DTE policy whose tie, missing-volume, holiday, contract-gap, and fallback behavior is explicit.
- **R6 — No lookahead:** Liquidity rolls use only volume from the prior observed trading session; current-session volume cannot decide the current-session contract.
- **R7 — Expiry guard:** A selected contract must have more than 3 calendar days to expiry when a later eligible contract exists. If the current contract reaches 3 DTE or less, roll to the nearest later eligible contract regardless of volume.
- **R8 — Crossover rule:** Roll on liquidity only after the next contract's prior-session volume is strictly greater than the current contract's prior-session volume for 2 consecutive observed sessions. Ties or missing volume reset confirmation and hold unless R7 forces a roll.
- **R9 — Gaps and fallback:** Holidays are skipped naturally because only observed sessions count. If the current contract disappears, advance to the nearest later eligible contract and record `contract_unavailable`; if no eligible later contract exists, fail closed.
- **R10 — Roll ledger:** Every contract change records trade date, old contract, new contract, trigger, old-contract DTE, prior current volume, prior next volume, and confirmation evidence.
- **R11 — Return integrity:** Never compute a return across different contracts; the first selected row and every roll boundary have a null return.
- **R12 — History evidence:** Persist a reproducible local Massive sample under ignored data storage and commit only non-market-data validation metadata/hashes plus the re-fetch procedure.
- **R13 — Licensing gate:** Do not mark Massive canonical backtest evidence allowed unless non-display/backtesting rights are verified for the user's account. Public-repo artifacts MUST NOT redistribute Massive market values.
- **R14 — Evidence gate:** Readiness checks require approved source, verified account history, implemented default roll policy, required roll inputs, raw-per-contract storage, no cross-contract returns, and verified licensing status.

## Verified Current-State Evidence

- GitHub and local `main` were synchronized to `dc344c029a39c9ad6d364c248c41cf42e06f2491` before this worktree was created.
- Massive credentialed contract discovery returned `status=OK`, pagination, NG contract metadata, expiration, and NYMEX venue identity.
- Live session aggregates for `NGU4`, `NGV4`, `NGX4`, and `NGF5` all begin at `2024-08-13`; `NGQ4` returns no aggregate rows. Rows contain settlement price, OHLC, volume, transactions, and session dates, with no historical open-interest field.
- `NGU4` contains all 12 weekdays from 2024-08-13 through 2024-08-28. Later row-count shortfalls align with major U.S. futures holidays; no unexplained hole has been established by the probe.
## Architecture and Data Flow

`commodity.massive` owns authenticated HTTP acquisition and provider normalization. `commodity.market_data` owns provider-neutral canonical readiness. `commodity.rolls` owns deterministic derived selection, roll ledger generation, and cross-contract return suppression. Configuration owns the selected policy and evidence prerequisites; CLI code only orchestrates these units.

## Boundaries and Exclusions

- Databento remains excluded.
- Historical open interest is not sourced, inferred, or fabricated in this slice.
- No LIVE-trading authority changes.
- No serious model training, feature expansion, or strategy optimization occurs here.
- The repository will not commit Massive raw market values while redistribution/non-display rights remain unresolved.

## Acceptance Evidence

- Targeted TDD proves header authentication, policy edge cases, ledger evidence, null roll-boundary returns, and fail-closed readiness.
- A local ignored sample is reproducibly re-fetchable and its committed manifest contains only coverage/provenance metadata and hashes.
- Full `pytest`, Ruff, and `git diff --check` pass on the final feature head.
- Final review reconciles R1–R14 and records any residual licensing blocker explicitly.

## Recovery

Revert the feature PR to restore the prior dual-liquidity candidate and blocked readiness state. Delete ignored validation samples independently if required. No migration or irreversible state transition is permitted.

## Specification Approval

The user's 2026-08-12 instruction explicitly approved this slice, preferred volume + expiry/DTE over sourcing separate OI, required fail-closed evidence validation, and prohibited serious training until the data contract is resolved. The licensing restriction discovered during validation is treated as a newly identified safety/legal gate rather than silently overridden.
