# Third-party Policy

This file owns approval, licensing, redistribution, and trust boundaries for external code and data. It does not own current provider readiness, model pins, dependency versions, or execution permission.

## Trust classes

- **Approved data source:** may be used for the stated research purpose subject to its licensing and point-in-time rules.
- **Approved dependency:** may execute inside Commodity within an explicitly bounded role. Exact versions belong to the lock/config owners.
- **Primary technical source:** owner-published SDK, protocol, or API implementation usable as integration evidence.
- **Discovery reference:** community material useful for patterns or source discovery but not authoritative for data semantics or rights.

A GitHub repository does not establish market-data truth, historical availability, or licensing rights. Community integrations must be traced back to the official underlying source before their semantics are adopted.

## Approved research-source families

Official U.S. EIA, CFTC, NOAA/NCEI and CME sources are approved for their relevant research roles. Databento historical data already purchased for this project is approved for private research/backtesting subject to integrity verification; raw licensed values remain local and redistribution is not approved. Massive Futures may be evaluated behind the provider boundary while its project-use rights remain subject to the recorded licensing decision.

European and Norwegian official/public-source families — including ENTSOG, GIE, ENTSO-E, Norwegian Offshore Directorate, Gassco, SSB, Statnett/NVE, MET Norway and Norges Bank — are approved for research evaluation/acquisition subject to their individual terms and point-in-time suitability.

Saxo OpenAPI/SIM may be used for bounded broker/instrument verification where approved, but that does not make it canonical backtest data or grant execution authority.

## Approved technical sources

| Source | Class | Approved use |
| --- | --- | --- |
| `shiyu-coder/Kronos` | Approved dependency | Bounded inference adapter only; exact model/code pins belong to `config/models.json` and lock/config owners |
| `databento/databento-python`, `databento/dbn` | Approved dependencies | Local Databento decoding and fixtures within the licensed-data boundary |
| `open-meteo/open-meteo` | Primary technical source | Official weather API/model-routing reference |
| `statisticsnorway/ssb-pxwebapidata`, `PxTools/PxWebApi` | Primary technical sources | Official SSB/PxWeb integration mechanics |
| `NVE/HydAPI` | Primary technical source | NVE hydrological API integration reference |
| `modelcontextprotocol/modelcontextprotocol`, `modelcontextprotocol/python-sdk`, `modelcontextprotocol/servers` | Primary technical sources | MCP protocol, SDK, and reference patterns |
| Community ENTSO-E/GIE/MCP wrappers | Discovery references | Adapter patterns and failure-mode discovery only; underlying official APIs remain authoritative |

## External model code

External forecasting/model repositories may be used only through bounded adapters. Model enablement, exact pins and runtime settings belong to `config/models.json`; dependency versions belong to repository lock files. Examples, web UIs, self-install helpers, training paths, unsafe deserialization paths, or other upstream components are not trusted merely because an inference package is approved.

## Licensing boundary

Licensed raw market values stay out of Git unless their terms explicitly permit repository storage. Commit only safe metadata, manifests, hashes, summaries, contracts, and decisions. Redistribution rights are separate from private research rights.

Operational source status and evidence gates are owned by `config/data_sources.json`. Desired data families and geographic acquisition architecture are described in `docs/data-manifest.md`.