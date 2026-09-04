<!-- GENERATED FILE. DO NOT EDIT. Source: config/data_sources.json -->

# Data Sources

Source: `config/data_sources.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 4 |
| `target` | CME Henry Hub Natural Gas futures |
| `canonical_market_source_id` | databento_henry_hub |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `target` | str |
| `providers` | object (11 keys) |
| `canonical_contract_schema` | object (8 keys) |
| `sources` | object (13 keys) |
| `source_library` | object (10 keys) |
| `canonical_market_source_id` | str |

## Sources

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
| `noaa_observed_weather` | noaa_ncei_observed_climate | public_source_route_verified_not_acquired | source-faithful observed weather and climatological-normal construction for descriptive Henry Hub literature reproductions |

## Candidate source library

Preserve the broader candidate-source and desired-dataset knowledge used to plan Commodity research. This library is the first stop for source discovery; current provider implementation, operational status, PIT admissibility, licensing approval, acquisition authority and backtest eligibility remain owned by providers/sources and their explicit evidence gates.

Candidate entries are discovery/planning knowledge only. They do not imply implementation, PIT safety, licensing approval, acquisition authority, backtest eligibility, or canonical-source status.

### Source register

| ID | Sources | Access | Primary use |
| --- | --- | --- | --- |
| `US-MKT` | Massive Futures, Databento GLBX.MDP3, CME Henry Hub | Massive API key; Databento API key; CME public specifications | Henry Hub contracts, settlement/statistics, expiry and market definition |
| `US-EIA` | EIA Open Data API | Free API key plus public Natural Gas bulk ZIP | Storage, production, demand, imports/exports, spot and EIA-930 power |
| `US-CFTC` | CFTC Commitments of Traders | Public | Henry Hub positioning; code 023651 |
| `US-SUPPLY` | EIA STEO/DPR, Baker Hughes Rig Count | Public | Rigs, drilling, DUCs and production-productivity estimates |
| `US-STORM` | NOAA NHC Data Archive, BSEE | Public | Issued tropical advisories and offshore shut-in/evacuation reports |
| `US-MACRO` | FRED, BEA, BLS | Public | Industrial and macro demand/regime data |
| `WX-ARCHIVE` | Open-Meteo, NOAA GFS, NOAA GEFS | Public; ECMWF historical archive remains a separate access/cost decision | Actually-issued forecast vintages and forecast-revision research |
| `EU-TTF` | ICE Dutch TTF Natural Gas Futures | Contract specs public; historical market data subject to entitlement | TTF market and curve |
| `EU-FX` | ECB Data Portal | Public API | EUR/USD and other cross-market reference FX |
| `EU-FLOW` | ENTSOG Transparency | Public | European gas flows and capacities |
| `EU-GIE` | GIE AGSI/ALSI | Free registration/API key | European storage and LNG terminals |
| `EU-IIP` | GIE Inside Information Platform | Public | Planned/unplanned gas storage and LNG inside information |
| `EU-PWR` | ENTSO-E Transparency Platform | Public registration/API token | Load, generation, renewables, hydro, outages and power prices |
| `EU-REMIT` | ACER REMIT Data Reference Centre | Public aggregated downloads | Gas/LNG trading structure and REMIT research data |
| `GLOBAL-JODI` | JODI-Gas World Database | Public | Monthly global production, trade, stocks and demand |
| `GLOBAL-JKM` | CME LNG Japan/Korea Marker | Contract metadata public; benchmark/history licensing to verify | JKM curve and TTF/HH spreads |
| `EU-TRADE` | Eurostat Comext | Free API/bulk | Detailed monthly gas trade by partner/product |
| `GLOBAL-LNG` | Kpler LNG | Commercial candidate | Cargo, vessel, freight and pipeline intelligence |
| `NO-PROD` | Norwegian Offshore Directorate FactPages | Public CSV/XML/Excel | Field-level and total NCS production |
| `NO-FLOW` | Gassco, Gassco FLOW/UMM | Public web; machine access/history depth to verify | Norwegian transport, maintenance and outages |
| `NO-SSB` | SSB PxWebApi v2 | Public, no registration, CC BY 4.0 | Exports/economy; tables 08864 and 08799 |
| `NO-PWR` | Statnett power-system data, NVE reservoir statistics | Public | Norwegian power, exchange and hydro state |
| `NO-WX` | MET Norway Weather API | Public with service terms | Norwegian observation/current forecast support |
| `NO-FX` | Norges Bank exchange rates | Public API | EUR/NOK, USD/NOK and other reference FX |
| `LIT-BHLR-RTDB` | Baumeister-Huber-Lee-Ravazzolo JAE Data Archive, Baumeister research page real-time database and replication code | Open research data and replication materials; article is CC BY-NC | Exact first-pass reproduction of Forecasting Natural Gas Prices in Real Time using authors' historical real-time vintages and code |
| `LIT-RS-EUUS` | Rubaszek-Szafranek Europe-US replication files, Author publication page | Replication files linked by authors; paper CC BY 4.0 | Exact first-pass reproduction of the European energy crisis / U.S. natural-gas structural VAR result |
| `US-STORAGE-CONSENSUS` | Bloomberg weekly natural-gas storage analyst consensus, S&P Global / Platts weekly U.S. gas storage survey, Estimize Weekly Natural Gas Storage | Bloomberg subscription is the source-faithful route used by key storage-surprise papers; Platts historical survey archive/licensing to verify; Estimize public pages/API surface with coverage and population fidelity to audit | Pre-release storage expectations for storage-surprise and announcement studies; Bloomberg is preferred for exact/near reproduction where the paper uses Bloomberg consensus, Platts is an independent analyst-survey route, and Estimize is a secondary distinct-population comparator |
| `LIT-GKS-ATTENTION-DATA` | Genesis Financial Technologies, Bloomberg | Subscription data; authors state both sources are available for a fee | Source-faithful data family for Gu-Kurov-Stan 2026 Friday trader-attention / natural-gas futures reaction study |
| `US-OIL` | EIA Cushing WTI spot history, EIA Cushing crude-oil futures contract histories | Public XLS/history | Deep-history WTI spot and prompt/fixed-rank futures candidates for oil-gas linkage replication and robustness |
| `US-LNG-EBB` | Energy Transfer pipeline informational postings, Golden Pass supply and transportation map | Public operator postings; archive/query depth and automated acquisition behavior must be audited per pipeline | Terminal-linked scheduled quantities, capacity and nominations as a public-path candidate for LNG feedgas/utilisation; terminal-to-pipeline mapping required |
| `US-WX-OBSERVED` | NOAA GHCN-Daily, NOAA U.S. Daily Climate Normals 1991-2020 | Public bulk/search access | Observed temperature/HDD/CDD departures from fixed climatological normals for source-faithful descriptive weather reproductions |

### U.S. / Henry Hub candidate families

| Family | Priority | Grain | Preferred sources | PIT / access note |
| --- | --- | --- | --- | --- |
| Primary Contract History | V1 | contract/day | provider-adapted source plus CME definitions | Use exact listed-contract identity and never compute returns across contract rolls; current approved market-source state remains in sources. |
| Issued Weather Forecasts | V1 | forecast run/hour to daily features | Open-Meteo issued-run archives; NOAA GFS/GEFS; ECMWF archive where approved | Use actually-issued vintages only; never substitute reanalysis. Preserve run identity and source availability. |
| Underground Storage | V1 | week/event | EIA WNGSR ngshistory.xls plus revisions.xls; API v2/bulk for screening | Reconstruct first-public values, later revisions, holiday releases and special revision events rather than backfilling corrected history. |
| Gas Production And Balance | V1 | month/region | EIA Natural Gas / API v2 | Apply actual publication lag and reconstruct historical revisions before backtest use. |
| Gas Demand And Power Burn | V1 | hour plus month/region | EIA Natural Gas; archived issued ISO load forecasts; EIA-930 screening | Prefer archived issued forecasts for strict PIT evidence; revised/final power history is screening-only unless vintages are reconstructed. |
| Lng And Pipeline Trade | V1 | month/point/country | EIA Natural Gas / API v2 | Public monthly data are the floor; publication/revision vintages must be reconstructed for strict PIT use. High-frequency feedgas is a separate candidate family. |
| Spot Reference Price | V1 | day | EIA Natural Gas / API v2 | Align to publication availability rather than trade date alone. |
| Calendar Seasonality | V1 | session | CME definitions, exchange/provider schedules and deterministic derived calendar | Derived calendar identity must be reproducible and contract semantics must remain exact. |
| Cftc Positioning | V1 | week | CFTC Disaggregated Futures Only; NYMEX code 023651 | Keep report-as-of date separate from publication availability; preserve special/catch-up release calendars. |
| Drilling And Supply Response | Later | week/month | EIA STEO/DPR plus Baker Hughes | Slow-moving supply response; preserve report vintage because productivity and DUC estimates can be revised. |
| Gulf Tropical Disruption | Later | advisory/day/event | NOAA NHC plus BSEE | Use issued advisories for forecasts; retain BSEE event publication time. |
| Storage expectations and forecast revisions | Later | forecast vintage/period or announcement event | EIA STEO plus licensed historical consensus candidate | Preserve every forecast vintage. Market-consensus history requires explicit licensing, historical-fixity and data-quality verification. |
| Macro Industrial Demand | Later | month/quarter | Federal Reserve/FRED, BEA, BLS | Use actual release timestamps and vintages where revisions occur. |
| Pipelines Outages Lng Feedgas | Later | hour/day/asset | pipeline EBBs; captured public notices; approved commercial aggregator | No single verified free historical vintage feed was established; preserve notice/update history and require explicit commercial-source approval where used. |
| Options Volatility Surface | Later | contract/strike/day | CME or licensed market-data vendor | Historical licensing/access decision required. |
| Substitution Cross Asset | Later | hour/day | EIA, CME and power-market sources | Acquire only for predeclared economic hypotheses; distinguish contemporaneous linkage from forecastable information. |

### Global / Interconnect candidate families

| Family | Priority | Grain | Preferred sources | PIT / access note |
| --- | --- | --- | --- | --- |
| Ttf Market And Curve | V1 | contract/day | ICE Dutch TTF futures | Official contract source; verify historical market-data entitlement/licensing before ingestion. |
| Cross Market Fx | V1 | day | ECB Data Portal | Reference rates are published on a schedule; use market FX instead when intraday timing requires it. |
| European Gas Transmission | V1 | hour/day/point | ENTSOG Transparency Platform | Preserve publication timestamps, corrections, point identities and capacity semantics. |
| European Storage | V1 | day/facility/country | GIE AGSI | Snapshot revisions and changing facility/EIC metadata. |
| European Lng Terminals | V1 | day/facility | GIE ALSI | Preserve facility identity, publication timing and revisions. |
| European Issued Weather Forecasts | V1 | forecast run/hour | Open-Meteo issued-run archives; NOAA global models | Use issued forecasts only; retain vintage and predeclare population/gas-demand weighting. |
| European Electricity System | V1 | 15-min/hour/day/bidding zone | ENTSO-E Transparency Platform | Keep source publication/revision state and bidding-zone identity. |
| Gas Lng Inside Information | V1 | event/asset | GIE IIP, ENTSOG/TSO notices, ACER REMIT sources | Event timestamps and every update are features; do not retain only final outage state. |
| Global Gas Balance | Later | month/country | JODI-Gas | Public global structural/regime layer; country revisions must be preserved or bounded. |
| Jkm Asian Lng Benchmark | Later | contract/day | CME JKM; Platts/licensed source if adopted | Benchmark methodology and historical price access are licensed; entitlement decision required. |
| Lng Cargo And Vessel Flows | Later | cargo/event | Kpler or equivalent commercial provider | High-value but commercial; acquire only after cost/licensing review and historical timestamp semantics are verified. |
| Lng Freight And Shipping Constraints | Later | day/route | Baltic, Clarksons, S&P or Argus candidates | Commercial/mixed access; source decision and timestamp semantics required. |
| Detailed Eu Gas Trade | Later | month/country | Eurostat Comext | Latest database is revised rather than vintage-versioned; preserve snapshot extracts. |
| Eu Gas Trading Structure | Later | quarter/market | ACER REMIT Data Reference Centre | Useful for regime/liquidity research rather than direct daily prediction. |
| Carbon And Coal Switching | Later | day | ICE/EEX/licensed market sources | Add only when fuel-switch hypotheses justify licensing effort. |

### Norway / Europe candidate families

| Family | Priority | Grain | Preferred sources | PIT / access note |
| --- | --- | --- | --- | --- |
| Ncs Gas Production | V1 | month/field | Norwegian Offshore Directorate FactPages | Deep current-state history exists but field-level historical vintages were not established; strict PIT use requires vintage reconstruction. |
| Norwegian Gas Transport | V1 | hour/day/point | Gassco plus ENTSOG | Gassco current/next-day nominations are high-frequency but retained final history is limited; ENTSOG is corroboration/control rather than automatically independent signal evidence. |
| Norwegian Maintenance Outages | V1 | event/asset | Gassco FLOW/UMM | Timestamped event revisions are valuable; historical event-vintage depth and automated acquisition must be verified before activation. |
| Gas Exports | V1 | month/country | SSB tables 08864 and 08799 via PxWebApi v2 | Public and CC BY 4.0, but Statbank history is revision-bearing; reconstruct release vintages for strict PIT use. |
| Nok Fx | V1 | day | Norges Bank open data API | Respect scheduled daily reference-rate availability. |
| Norwegian Power And Hydro | Later | 15-min/hour/week/zone | ENTSO-E, Statnett, NVE | Preserve source publication/revision state and avoid double-counting series originating from ENTSO-E. |
| Norwegian Weather | Later | hour/station/grid | MET Norway; Open-Meteo/NOAA for archived issued forecasts | Observations are truth data, not substitutes for historical issued forecast vintages. |
| Upstream Capacity And Resources | Later | field/well/event | Norwegian Offshore Directorate | Structural/regime features rather than short-horizon signals; preserve update identity. |
| Investment And Drilling | Later | quarter/month | SSB plus Norwegian Offshore Directorate | Publication/revision timestamps required. |
| Norwegian Macro Export Transmission | Later | month/quarter | SSB plus Norges Bank | Primarily explanatory/regime variables; avoid features that merely restate gas-price outcomes. |
| Operator Forward Export Estimates | Later | forecast vintage/field | Gassco GMDC candidate | Operational data may exist, but public historical machine access was not established; eligibility remains unresolved. |
