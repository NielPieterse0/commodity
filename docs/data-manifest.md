<!-- GENERATED FILE. DO NOT EDIT. Source: config/data_sources.json, config/research_dataset.json, data/acquisition-recipes/*.json -->

# Data Architecture

Source: `config/data_sources.json`

## Canonical contract

Grain: `one row per trade_date and contract_id`

Required columns: `trade_date`, `contract_id`, `expiration`, `settle`

## Current sources

| Source | Provider | Status | Purpose |
| --- | --- | --- | --- |
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
