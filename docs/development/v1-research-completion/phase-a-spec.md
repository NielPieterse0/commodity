# V1 Research Completion — Phase A Specification

Program: GitHub issue #15. Phase A: #17. Baseline: verified Phase 0 head `7b8546a3273a6c662848e0e285ca70559a2f7921`.

## Goal
Make canonical Henry Hub per-contract history produce a deterministic, point-in-time market representation and market-structure feature family without weakening provider, licensing, or evidence controls.

## Requirements
- **R1 — PIT contract panel:** Validate contract identity, expiry, session date, settlement and volume. Availability must be either a preserved source timestamp or an explicit source-configured conservative reconstruction; curve inputs later than the prediction cutoff must not enter features.
- **R2 — Deterministic roll:** Use only the roll policy owned by `config/assumptions.json`; retain source contract identity, roll trigger, prior-session evidence, and no cross-contract returns.
- **R3 — Market structure:** Derive deterministic M1–M4 settlement/DTE identities plus front spreads, curve slope and front/second volume ratio from admissible same-session contracts.
- **R4 — Dataset integration:** Canonical dataset construction automatically adds `market_structure`; proxy/research-PIT mode cannot claim that family from canonical contracts.
- **R5 — Lineage:** Manifest hashes bind canonical contract input, selected path, roll ledger, curve feature/audit artifacts, the owned roll policy, and market semantics (availability rule, exchange, product, session timezone, calendar, adjustment/storage semantics); synthetic continuous representation is explicitly labeled derived/non-tradable.
- **R6 — Provider neutrality:** No core market/dataset code may depend on Massive- or Databento-specific implementation details.
- **R7 — Cross-source honesty:** Existing Databento material remains quarantined. Cross-source evidence may be diagnostic only; absent an integrity-verified overlap with Massive, record that no promotable cross-source agreement result exists.

## Acceptance evidence
- Unit tests prove late quote exclusion, deterministic rank/curve derivation, roll-boundary null returns, and fail-closed missing availability/volume.
- Canonical dataset tests prove complete M1–M4 `market_structure` inclusion, fail-closed incomplete rank evidence, roll-boundary target exclusion, and deterministic lineage hashes.
- Existing provider-neutral adapter tests remain green.
- A bounded local audit of the preserved Massive M1–M12 snapshot confirms the derivation executes deterministically; it must not be promoted to backtest evidence while licensing remains blocked.
- Cross-source status is recorded without using quarantined Databento values as research evidence.
- Full repository tests, Ruff, diff check and secret scan pass on the exact Phase A head; independent review has no blocking finding.

## Exclusions and external blockers
- No paid acquisition or Databento re-download.
- No change to `config/policy.json` LIVE authority.
- No claim that Massive is legally usable for backtesting while `non_display_backtesting_rights_verified=false` or `backtest_evidence_allowed=false`.
- Storage, weather, power and positioning promotion belongs to Phase B.
- A licensing blocker may prevent canonical research promotion, but it does not permit weakening R1–R7.
