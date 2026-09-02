<!-- GENERATED FILE. DO NOT EDIT. Source: config/data_sources.json -->

# Data Sources

Source: `config/data_sources.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 3 |
| `target` | CME Henry Hub Natural Gas futures |
| `canonical_market_source_id` | databento_henry_hub |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `target` | str |
| `providers` | object (10 keys) |
| `canonical_contract_schema` | object (8 keys) |
| `sources` | object (12 keys) |
| `canonical_market_source_id` | str |

## Sources

| Source | Provider | Status | Purpose |
| --- | --- | --- | --- | --- |
| `market_bootstrap` | yfinance | research_bootstrap | daily OHLCV proxy |
| `saxo_henry_hub_probe` | saxo_openapi_sim | sim_verification_pending | verify Henry Hub futures-space identity and historical chart depth |
| `eia_nymex_prompt_history` | eia_api_v2 | historical_term_structure_candidate | daily NYMEX prompt-contract closes for contract ranks 1-4 |
| `eia_storage` | eia_wngsr | v1_research_evaluation_ready | null |
| `eia_fundamentals` | eia_api_v2 | capture_ready_current_snapshot_only | production, balance, gas demand, LNG/pipeline trade and Henry Hub spot/reference price |
| `eia_power` | eia_api_v2 | targeted_snapshot_ready | Lower-48 hourly demand/day-ahead demand forecast and natural-gas generation |
| `nyiso_load_forecast` | nyiso_mis | v1_research_evaluation_ready | PIT-admissible issued NYISO load forecasts for the V1 power feature family |
| `cftc_cot` | cftc_public_reporting | v1_release_reconstruction_ready | weekly PIT Henry Hub positioning; Managed Money is the preferred research slice |
| `weather` | open_meteo_historical_forecast | v1_research_evaluation_ready_with_declared_gaps | forecast-vintage temperatures and HDD/CDD surprises by gas-demand region |
| `noaa_gfs_weather_revision` | noaa_gfs_archive | feasibility_hold_source_audit_required | PIT issued 00 UTC GFS 2-m-temperature forecast revisions for a mechanism-led Henry Hub response experiment |
| `massive_henry_hub_evaluation` | massive_futures | history_and_roll_validated_evaluation_only | retained V1 expiry-aware NYMEX NG per-contract evaluation history; not canonical promotion evidence |
| `databento_henry_hub` | databento_futures | acquired_integrity_complete_research_approved | canonical private-project CME NG official settlement/statistics and deep contract history for research and backtesting |
