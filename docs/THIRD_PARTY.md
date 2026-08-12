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

### Historical CME data boundary

CME DataMine is not an approved repository dependency under the current free-service constraint. A future canonical contract-history provider requires explicit source, licensing, cost, and point-in-time review before `market_canonical` may be promoted.
