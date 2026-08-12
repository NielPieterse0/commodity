# Third-party source policy

## Kronos

- Upstream: `shiyu-coder/Kronos`
- Pin: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`
- License: MIT
- Approved initial scope: `model` inference classes only.
- Default model: defined only in `config/models.json`.

### Excluded pending explicit review

- `webui/`: may launch subprocesses and install dependencies.
- `examples/`: includes network calls and self-install helpers.
- `finetune/` and `finetune_csv/`: include pickle deserialization and training-specific behavior.

The Commodity adapter SHALL import only the approved inference module. Upstream examples, web UI, and finetuning code are not trusted runtime dependencies.

## Research data sources

Operational status, point-in-time requirements, and evidence gates are owned by `config/data_sources.json`.

- **U.S. EIA** — approved for free research data acquisition through official EIA interfaces.
- **U.S. CFTC** — approved for public COT research data acquisition through official CFTC interfaces.
- **NOAA/NCEI** — approved for historical forecast-vintage weather research through official NOAA/NCEI archives.
- **CME Group** — approved as the authoritative contract-specification and market-definition reference.
- **Saxo OpenAPI SIM** — approved only for read-only instrument/futures-space/chart-depth verification. It is not an approved canonical backtest source and is not an execution adapter.
- **Massive Futures** — approved for expiry-aware NG contract discovery and per-contract session settlement/OHLCV price ingestion through the configured account. It is not yet approved for canonical backtest evidence because available history is plan-dependent and the documented historical aggregate endpoint does not provide per-contract open interest required by the current candidate roll rule. Primary references: [Contracts](https://massive.com/docs/rest/futures/contracts) and [Aggregate Bars](https://massive.com/docs/rest/futures/aggregates).

### Saxo market-data boundary

Saxo futures-space metadata may establish contract identity/UIC/expiry availability. Saxo chart samples expose historical OHLC/volume/interest and `FirstSampleTime`, but are not treated as official settlement. Canonical promotion requires verified Henry Hub coverage, defensible expired-contract depth, and compatible price semantics.

### Historical CME data boundary

Massive Futures is the selected canonical per-contract price-history source. Its aggregate endpoint provides session settlement, OHLC and volume, while account history depth depends on the active Massive plan. No paid plan upgrade is approved by this repository decision; the cost preference remains a revisable assumption owned by `config/assumptions.json#assumptions.service_cost`.

Canonical backtest evidence remains blocked because `dual_liquidity_crossover` requires historical per-contract open interest and Massive's documented historical aggregate response does not expose that field. Databento remains explicitly excluded from the current slice by `config/assumptions.json#assumptions.canonical_market_provider`.
