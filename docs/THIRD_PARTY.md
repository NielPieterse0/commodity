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
- **Massive Futures** — approved for expiry-aware NG contract discovery and per-contract session settlement/OHLCV acquisition through the configured account. The live account was validated on 2026-08-12 with aggregate history observed from 2024-08-13 and no historical per-contract open-interest field. The canonical roll methodology no longer depends on OI. Canonical **backtest** evidence remains blocked because Massive's individual Market Data Terms default market data to display use and require separate permission for non-display use / investment-strategy derived works. Primary references: [Contracts](https://massive.com/docs/rest/futures/contracts), [Aggregate Bars](https://massive.com/docs/rest/futures/aggregates), and [Market Data Terms](https://massive.com/legal/market-data-terms-of-service).

### Saxo market-data boundary

Saxo futures-space metadata may establish contract identity/UIC/expiry availability. Saxo chart samples expose historical OHLC/volume/interest and `FirstSampleTime`, but are not treated as official settlement. Canonical promotion requires verified Henry Hub coverage, defensible expired-contract depth, and compatible price semantics.

### Historical CME data boundary

Massive Futures is the selected canonical per-contract price-history source. The configured account exposes session settlement, OHLC and volume with an observed common history boundary beginning 2024-08-13 as verified on 2026-08-12; that is consistent with Massive's currently documented two-year individual tiers, but the repository does not infer the account plan from this observation. The raw per-contract sample is stored only in ignored local data; the repository commits capability/provenance metadata and hashes, not Massive market values.

The registered canonical roll policy is now `volume_crossover_dte_v1`: two consecutive prior-observed-session strict volume crossovers, with a forced roll at 3 calendar DTE and fail-closed gap handling. Open interest is not required. Canonical backtest promotion is still blocked solely by the unresolved non-display/backtesting entitlement. Databento remains explicitly excluded by `config/assumptions.json#assumptions.canonical_market_provider`.
