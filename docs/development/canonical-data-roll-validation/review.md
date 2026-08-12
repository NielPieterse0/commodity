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

## External Review Closeout

A subsequent external review identified one required governance defect and seven suggestions. Disposition on the current branch:

- **ER-01 / required:** FIXED. `assert_execution_mode` now reads `execution.live_trading_allowed` and still requires the requested mode to appear in `allowed_modes`. The authoritative policy remains `live_trading_allowed: false`.
- **ER-02:** CLARIFIED. `research_stages.json` and `tools.json` are authoritative governance/agent owners, not required forecast-runtime inputs; README now states that distinction rather than adding unused runtime accessors.
- **ER-03:** FIXED. `walk_forward_predict` rejects `retrain_every < 1` with `ValueError`.
- **ER-04:** FIXED. `config/models.json` now owns baseline family, architecture and implementation identity; CLI baseline choices and construction are config-driven and unknown implementations fail closed; experiment records consume configured family/architecture.
- **ER-05:** FIXED. `research_period.end = "2100-01-01"` now carries explicit `open_ended_far_future_sentinel` semantics and a contract test.
- **ER-06:** DEFERRED. Emitting a `no_active_contract` row would change the derived-series contract without an approved trading-session/gap model. Revisit when session-calendar and missing-session semantics are specified; canonical evidence remains blocked meanwhile.
- **ER-07:** FIXED. Repeated `KronosMiniAdapter` construction no longer duplicates its vendor import path.
- **ER-08:** FIXED. The canonical product-code override test now asserts the explicit argparse rejection text, and the parser documents that product code is config-owned.

Fresh closeout review found no surviving P0-P3 correctness issue in R11-R15. Independent reviewer retries were not counted as passes: Codex failed with `AGENT_BACKEND_FAILED:UnicodeEncodeError`; the configured NVIDIA reviewer failed with `AGENT_BACKEND_FAILED:NvidiaNimError`.

## External Closeout Modularity Assessment

Mode A, 90-day horizon, all six changed implementation units sampled. Collector measured 3 relevant commits; `cli.py` is the largest unit at 222 LOC with measured fan-out 12, while the other units remain 20-130 LOC. Read-set/edit-set, test isolation and clustered RFC kinds remain unmeasured, so evidence strength is **LOW** and MAS is `n/a`.

No new split or merge is justified. Moving baseline construction into `commodity.models` reduces model-specific CLI responsibility and follows the existing ownership boundary. `cli.py` remains the only monitor item: reassess if provider/model business logic continues accumulating there or if independent change history becomes available.
