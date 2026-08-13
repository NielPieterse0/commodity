# Canonical Market Provider Boundary Review

## Conclusion

The current Massive dataset is useful primarily for futures-market definition: exchange settlement, per-contract volume, expiry identity, and a clean term structure. It has not yet demonstrated incremental next-session return or direction signal over simpler price features. The small absolute-return improvement from M1-M12 curve features is not statistically decisive on the two-year sample.

The runtime boundary is now provider-neutral. Core CLI and market-domain code do not import or name Massive; the concrete implementation is isolated in `commodity.massive_futures_provider` and loaded by configured provider id through a two-method protocol. A future provider swap does not require changes to core CLI behavior.

## Subscription decision

- **Basic ($0): keep using for evaluation.** The two-year API history is sufficient for the current bounded research path.
- **Starter ($29): do not buy for history.** It retains the same two-year history; its primary benefit here is throughput/flat-file access.
- **Developer ($79): only paid tier worth a bounded next test.** Five years of history would materially improve regime coverage and let us test whether the weak volatility result survives a larger sample.
- **Advanced ($199): not justified now.** Real-time data and 7+ years/all-history access should wait until five-year evidence and licensing justify the cost.

Current official plan facts were checked on 2026-08-13 against `https://massive.com/pricing?product=futures` and `https://massive.com/docs/flat-files/futures/session-aggregates/nymex`.

## Dataset evidence

- Preserved snapshot: 500 sessions, 11,200 canonical rows, 2024-08-14 through 2026-08-12.
- Intended M1-M12 panel: 5,988 / 6,000 cells present (99.8%).
- Old capture semantics over-stored 5,209 rows beyond M12 (46.51% of rows); the new capture uses expiry-rank membership per trade date.
- Rank-window formula was cross-checked against exact active-contract membership for all 172 discovered NG contracts across 730 calendar days in the audit range: 0 mismatch days.
- Settlement differs from session close on 5,840 / 5,988 M1-M12 rows (97.53%), confirming settlement is not a redundant close-price alias.
- M2 volume exceeds M1 on 100 / 500 sessions (20%), supporting contract-level volume as roll evidence.
- Screening-only OOS return and direction tests did not improve on simple references; M1-M12 absolute-return RMSE improved only from 0.033159 to 0.032978 versus price-only, with block-bootstrap 95% delta spanning zero.

Raw licensed values remain ignored and outside Git. Aggregate evidence is pinned by SHA-256 in `evidence.json`.

## Licensing gate

Massive individual market-data terms restrict use to personal, non-business/non-commercial purposes and restrict non-display/derived use absent appropriate licensing. The repository therefore continues to record `non_display_backtesting_rights_verified=false`, `redistribution_allowed=false`, and canonical backtest evidence disabled. No licensing or execution authority changed in this slice.

## Code review

Two findings were closed during review:

1. **Adapter import masking:** the loader originally converted any adapter-internal import failure into “adapter unavailable.” It now converts only a missing adapter module and propagates dependency/import failures unchanged.
2. **Default pacing:** the loaded Massive provider originally paced archive capture but not generic history fetch. The provider factory now constructs a client with the configured minimum request interval for both interface methods.

The previous absolute-expiration capture boundary was replaced with provider-neutral contract-rank windows. Checkpoint requests include `max_contracts`, so a changed curve bound cannot silently resume an incompatible capture.

## Modularity assessment

Mode A structural collection was run on the changed runtime units with 90-day history and file granularity. Measured fan-in/fan-out: `canonical_provider.py` 2/0, `market_data.py` 6/0, `massive_futures_provider.py` 2/4, and `cli.py` 0/14. RFC-kind clustering, hidden coupling, and read-set/edit-set remain unmeasured, so a formal MAS score is intentionally not claimed.

The provider boundary is a declared contract rather than layout reach-through. Runtime search confirms concrete Massive references are confined to `src/commodity/massive_futures_provider.py`; core CLI and market-domain code are provider-neutral. The 547-line adapter remains intentionally cohesive around one replaceable vendor; splitting REST transport, normalization, and preservation further would not improve provider removal and would add indirection.

## Removal surface

If Massive is rejected later, remove or replace the following bounded surfaces:

- `src/commodity/massive_futures_provider.py`
- Massive provider/source entries in `config/data_sources.json`
- `MASSIVE_API_KEY` and Massive comments in `.env.example`
- `tests/test_massive.py` and `tests/test_massive_regressions.py`
- current provider-specific approval/evidence references such as `docs/THIRD_PARTY.md` and this development evidence
- ignored local `data/raw/snapshots/massive/` values if retention is no longer permitted or useful

Historical development records that describe earlier Massive evaluation are evidence of past repository decisions, not runtime dependencies. If the future decision is to remove the vendor name literally everywhere, a repository-wide case-insensitive search can identify those records for deletion or neutralization without changing core runtime code.

## Verification

- Provider/market/CLI focused suite: 37 passed after review fixes.
- Local scratch full suite: 107 passed in 7.60s.
- Ruff: clean.
- `git diff --cached --check`: clean.
- Staged-diff secret-pattern scan: 0 hits.
- Independent review backends were attempted but unavailable: Codex CLI failed with `UnicodeEncodeError`; NVIDIA NIM failed with a provider error. No external-review result is claimed.
- Exact remote-base integration and GitHub CI remain required at final PR head.
