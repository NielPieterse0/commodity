<!-- GENERATED FILE. DO NOT EDIT. Source: config/third_party.json, config/models.json, config/data_sources.json, .gitmodules -->

# Third-party Policy

Source: `config/third_party.json`

## Trust classes

- **approved_data_source** — May be used for the stated research purpose subject to licensing and point-in-time rules.
- **approved_dependency** — May execute inside Commodity within an explicitly bounded role; exact versions belong to lock/config owners.
- **primary_technical_source** — Owner-published SDK, protocol, or API implementation usable as integration evidence.
- **discovery_reference** — Useful for patterns or source discovery but not authoritative for data semantics or rights.

## Technical sources

| Source | Class | Use |
| --- | --- | --- |
| `shiyu-coder/Kronos` | `approved_dependency` | bounded inference adapter |
| `google-research/timesfm` | `approved_dependency` | bounded forecasting adapter |
| `databento/databento-python` | `approved_dependency` | local Databento decoding |
| `databento/dbn` | `approved_dependency` | local DBN decoding and fixtures |
| `open-meteo/open-meteo` | `primary_technical_source` | official weather API/model-routing reference |
| `statisticsnorway/ssb-pxwebapidata` | `primary_technical_source` | official SSB/PxWeb integration mechanics |
| `NVE/HydAPI` | `primary_technical_source` | NVE hydrological API integration reference |
| `modelcontextprotocol/*` | `primary_technical_source` | MCP protocol, SDK, and reference patterns |

## Licensing

Licensed raw market values stay out of Git unless terms explicitly permit repository storage; private research rights do not imply redistribution rights.
