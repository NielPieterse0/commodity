# Third-party source policy

This file owns third-party approval, licensing boundaries, and the GitHub API/MCP technical-source registry. Operational provider status and evidence gates are owned by `config/data_sources.json`; the repository-wide ownership map is `AGENTS.md`.

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

## Technical-source classes

- `primary_technical`: owner-published code, SDK, protocol, or API implementation usable as primary evidence for integration mechanics.
- `discovery_reference`: community code usable for adapter patterns, feature ideas, failure modes, and source discovery only.
- `dependency`: code imported or vendored by Commodity; requires an explicit pin, license review, and bounded runtime scope.

A GitHub repository does not establish market-data truth, licensing rights, historical availability, or evidence promotion by itself. Community API/MCP repositories MUST be traced back to the underlying official source before their data semantics are adopted.

## Research data sources

Operational status, point-in-time requirements, and evidence gates are owned by `config/data_sources.json`.

- **U.S. EIA** — approved for free research data acquisition through official EIA interfaces.
- **U.S. CFTC** — approved for public COT research data acquisition through official CFTC interfaces.
- **NOAA/NCEI** — approved for historical forecast-vintage weather research through official NOAA/NCEI archives.
- **CME Group** — approved as the authoritative contract-specification and market-definition reference.
- **Saxo OpenAPI SIM** — approved only for read-only instrument/futures-space/chart-depth verification. It is not an approved canonical backtest source and is not an execution adapter.
- **Massive Futures** - approved for expiry-aware NG contract discovery and per-contract historical market-data acquisition. Project-use rights for non-display/backtesting remain unresolved; current account coverage and canonical-evidence status are owned by `config/data_sources.json`. Primary references: [Contracts](https://massive.com/docs/rest/futures/contracts), [Aggregate Bars](https://massive.com/docs/rest/futures/aggregates), and [Market Data Terms](https://massive.com/legal/market-data-terms-of-service).
- **Databento Historical** - approved for bounded CME `GLBX.MDP3` NG research acquisition/evaluation. Acquisition does not itself approve a provider switch, project-use rights, redistribution, or canonical evidence. Acquisition and post-repair integrity evidence are recorded in [`docs/development/databento-full-history-acquisition/`](development/databento-full-history-acquisition/); operational provider status remains owned by `config/data_sources.json`. Primary references: [GLBX.MDP3](https://databento.com/datasets/GLBX.MDP3), [Statistics schema](https://databento.com/docs/schemas-and-data-formats/statistics), [Symbology](https://databento.com/docs/standards-and-conventions/symbology), and [Historical API](https://databento.com/docs/api-reference-historical).
- **European/Norwegian public-source set** - ENTSOG, GIE, ENTSO-E, Norwegian Offshore Directorate, Gassco, SSB, Statnett/NVE, MET Norway, and Norges Bank are approved for research evaluation/acquisition. Desired datasets and access notes are owned by `docs/data-manifest.md`.

### Saxo market-data boundary

Saxo futures-space metadata may establish contract identity/UIC/expiry availability. Saxo chart samples expose historical OHLC/volume/interest and `FirstSampleTime`, but are not treated as official settlement. Canonical promotion requires verified Henry Hub coverage, defensible expired-contract depth, and compatible price semantics.

### Historical CME data boundary

Massive and Databento may both be retained as replaceable research inputs. This file owns only their approval/licensing boundary; `config/data_sources.json` owns which source is configured and every operational evidence flag. Project-use and redistribution rights remain separate gates.

Licensed raw market values stay ignored from Git. Commit only safe manifests, hashes, coverage/integrity evidence, and decisions. The continuous-series/roll decision is owned by `config/assumptions.json#assumptions.continuous_series_policy` and is intentionally not repeated here.

## GitHub API/MCP technical-source registry

These repositories are approved **project research sources**, not automatically approved dependencies or data authorities. Re-evaluate freshness before implementation and pin a release/commit if code is adopted.

| Repository | Class | Project use |
|---|---|---|
| [`databento/databento-python`](https://github.com/databento/databento-python) | `dependency` | `databento==0.83.0`, Apache-2.0. Official client used only for local `DBNStore` decoding; the offline path does not construct a Historical/API client or change data-rights/evidence gates. |
| [`databento/dbn`](https://github.com/databento/dbn) | `dependency` | `databento-dbn==0.65.0`, Apache-2.0. Official DBN binding used by the pinned client and deterministic DBN fixtures. |
| [`indygreg/python-zstandard`](https://github.com/indygreg/python-zstandard) | `dependency` | `zstandard==0.25.0`, BSD-3-Clause. Compression runtime/test support for `.dbn.zst`; no market-data semantics are delegated to it. |
| [`open-meteo/open-meteo`](https://github.com/open-meteo/open-meteo) | `primary_technical` | Official API implementation; weather-model routing and historical/single-run behavior. |
| [`statisticsnorway/ssb-pxwebapidata`](https://github.com/statisticsnorway/ssb-pxwebapidata) | `primary_technical` | SSB-owned PxWeb API client/reference, including v2 query patterns. |
| [`PxTools/PxWebApi`](https://github.com/PxTools/PxWebApi) | `primary_technical` | Official PxWeb API source; platform semantics behind statistical APIs such as SSB. |
| [`NVE/HydAPI`](https://github.com/NVE/HydAPI) | `primary_technical` | NVE-owned HydAPI examples for Norwegian hydrological access. |
| [`modelcontextprotocol/modelcontextprotocol`](https://github.com/modelcontextprotocol/modelcontextprotocol) | `primary_technical` | MCP protocol/specification source. |
| [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) | `primary_technical` | Official Python MCP client/server SDK and transport semantics. |
| [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers) | `primary_technical` | Official reference servers; patterns only, not production-ready integrations. |
| [`EnergieID/entsoe-py`](https://github.com/EnergieID/entsoe-py) | `discovery_reference` | Community ENTSO-E client; useful for query coverage, parsing, pagination, and failure-mode patterns. |
| [`yannikbuhl/gie`](https://github.com/yannikbuhl/gie) | `discovery_reference` | Community GIE AGSI/ALSI/IIP wrapper; useful for storage/LNG endpoint, pagination, and facility-metadata patterns. |
| [`pipeworx-io/mcp-entso-e`](https://github.com/pipeworx-io/mcp-entso-e) | `discovery_reference` | ENTSO-E MCP adapter covering price, load, generation, capacity, and cross-border-flow tools. |
| [`sbudai/entsoeapi.mcp`](https://github.com/sbudai/entsoeapi.mcp) | `discovery_reference` | Independent ENTSO-E MCP implementation for comparing tool contracts and integration approaches. |
| [`adambenhassen/euenergy-mcp`](https://github.com/adambenhassen/euenergy-mcp) | `discovery_reference` | Read-only European electricity MCP; useful for bidding-zone, UTC, and partial-data handling patterns. |
| [`jo20ow/obsyd`](https://github.com/jo20ow/obsyd) | `discovery_reference` | Integrated European electricity research desk; useful for feature/ingestion architecture, not upstream data truth. |

These community discoveries strengthen the planned European modeling layer by exposing practical interfaces for prices, load, generation, cross-border flows, storage/LNG, and outage-style information. They do not promote Global/Interconnect or Norway/Europe onto the current training critical path; `docs/data-manifest.md` owns that sequence and the underlying official APIs remain the data authorities.
