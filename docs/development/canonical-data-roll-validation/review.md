# Canonical Data and Roll Validation Review

## Code Review

Change boundary: `main` to the current `feat/canonical-data-roll-validation` working tree.

Closed findings:

- **CR-01:** `assert_canonical_market_ready` accepted any non-empty roll policy. Fixed by permitting only the implemented `dual_liquidity_crossover` and testing the rejection path.
- **CR-02:** `doctor` reported the source-level evidence flag instead of the full readiness gate. Fixed by evaluating `assert_canonical_market_ready` and reporting the blocking reason.
- **CR-03:** `fetch-canonical-market` allowed arbitrary product codes despite the NG-only repository mandate. Fixed by binding the command to `config/data_sources.json#sources.market_canonical.product_code`.
- **CR-04:** invalid/missing `last_trade_date` could be silently omitted during canonical ingestion. Fixed by failing closed with `DataContractViolation`.

Final read-only review: no surviving P0-P3 correctness findings in the changed behavior.

## Modularity Review

Mode: A plus direct inspection. Horizon: 90 days. Subject: changed Python implementation units.

Collector command:
`python C:\Projects\.agents\skills\modularity-assessment\scripts\seams.py --repo . --since "90 days ago" --granularity file --unit src/commodity/providers.py --unit src/commodity/market_data.py --unit src/commodity/cli.py --top 10 --format md`

Evidence strength: **LOW**. The repository has only two relevant historical commits, and read-set/edit-set plus isolation evidence are unavailable; MAS is therefore `n/a`.

Observed finding:

- **MOD-01 / UD-1:** Massive-specific HTTP, normalization, and ingestion responsibilities were split across generic `providers.py` and `market_data.py`. Closed by creating cohesive `src/commodity/massive.py` and consolidating Massive tests in `tests/test_massive.py`.

Post-fix structure:

- `commodity.massive`: Massive API access, response normalization, and canonical Massive ingestion.
- `commodity.market_data`: provider-neutral canonical validation, term structure, and evidence readiness.
- `commodity.providers`: EIA/CFTC clients, shared credential error, and point-in-time dataset gate.
- `commodity.cli`: command orchestration only.

No additional decomposition is justified with current evidence. Reassess if `commodity.massive` gains independent feature/execution responsibilities or the CLI accumulates provider-specific business logic.

## Review Limitations

The Superpowers `requesting-code-review` workflow expects an independent reviewer. A Codex reviewer wrapper was attempted after the local specialist review, but its backend failed with `AGENT_BACKEND_FAILED:UnicodeEncodeError`. The installed read-only `code-review` specialist therefore remains the completed review gate; the failed wrapper is recorded rather than represented as an independent-agent pass.
