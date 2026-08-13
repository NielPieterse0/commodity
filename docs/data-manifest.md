# Natural Gas Data Manifest

**Research date:** 2026-08-13

This manifest defines the desired research dataset and acquisition roadmap. [`config/data_sources.json`](../config/data_sources.json) remains authoritative for implemented providers, source status, canonical-evidence gates, and point-in-time readiness. Verified local preservation metadata lives in [`docs/development/us-v1-data-foundation/evidence.json`](development/us-v1-data-foundation/evidence.json).

`V1` means the minimum serious dataset for the named layer. Only **U.S. / Henry Hub V1** is on the current training critical path; Global/Interconnect and Norway/Europe V1 define later layers so sources can be wired without redesigning the data model.

## Data contract

Every time-varying input should preserve `observed_for`, `published_at` or `issued_at`, `available_at`, `retrieved_at`, source identity/version, units, and revision state when the source supports them. Backtests may use a value only after `available_at`. Revised or final historical values must not replace the value that was knowable at prediction time.

Derived features are reproducible transformations, not new sources. Raw source values remain retained and versioned. A preserved current-state historical snapshot is **not** point-in-time backtest evidence unless its historical publication/revision availability has also been reconstructed.

The implemented availability layer distinguishes `canonical`, `research_pit`, and `screening` evidence. Conservative publication-time reconstruction does not erase revision risk: current revised EIA histories remain screening-only until historical vintages are recovered, while immutable issued-weather runs may qualify for `research_pit` with conservative availability timing. Massive market evidence remains independently gated by entitlement.

## 1. U.S. / Henry Hub

| Priority | Data family | Ideal datapoints | Grain | Preferred source | Access / point-in-time note |
|---|---|---|---|---|---|
| V1 | Futures contracts and curve | `contract_id`, expiry, settle, OHLC, volume; M1-M12 rank, spreads, slope, curvature, roll state | Contract/day | Massive Futures; CME for contract definitions | Massive key; selected source. Account history is validated from 2024-08-13. Resumable paced preservation is implemented and V1 market-value capture is bounded to M1-M12. Historical OI is unavailable but not required by `volume_crossover_dte_v1`. Canonical backtest use remains blocked pending non-display/backtesting entitlement; Massive values are not redistributed or committed. |
| V1 | Issued weather forecasts | issue/available/valid time, lead, 2m temperature, HDD/CDD, wind, humidity, precipitation/snow; forecast revisions; demand-region weights | Forecast run/hour -> daily features | Open-Meteo Single Runs; NOAA GFS/GEFS fallback | Open/public adapter implemented and an archived ECMWF run verified. Model initialization and valid time remain distinct from availability. For immutable issued runs, the research layer applies a conservative global-model delay of 6 hours plus a 10-minute consistency margin; this may support `research_pit`, but exact historical source availability remains unverified and is required for canonical evidence. Demand-region archive expansion remains required. Never use reanalysis as a forecast substitute. |
| V1 | Underground storage | working gas total + EIA regions, weekly injection/withdrawal, capacity, 5-year normal/deviation, release/revision timestamp | Week/region | EIA WNGSR / API v2 + Natural Gas bulk snapshot | Current Natural Gas bulk history is preserved. The regular Thursday 10:30 Eastern schedule plus published 2025-2026 holiday exceptions is encoded with bounded coverage. Current historical values remain revision-bearing, so they are screening-only until original/revised vintages are reconstructed; capture future releases as vintages. |
| V1 | Gas production and balance | dry, marketed and gross production; state/region; supply/disposition; offshore production | Month/region | EIA Natural Gas / API v2 | Current Natural Gas bulk history is preserved. Apply actual publication lag and reconstruct historical revisions before backtest use. |
| V1 | Gas demand and power burn | residential, commercial, industrial and electric-sector gas use; actual/forecast electricity load, generation by fuel, interchange | Hour + month/region | EIA Natural Gas + EIA-930 | Natural Gas bulk plus bounded Lower-48 EIA-930 demand/day-ahead forecast and NG-generation snapshots are preserved for 2024-08-13 through 2026-08-12. Field-specific EIA-930 publication timing is reconstructed conservatively, but the current historical API snapshot remains revision-bearing and therefore screening-only until historical revisions/vintages are reconstructed. |
| V1 | LNG and pipeline trade | LNG exports, pipeline imports/exports, country, point of entry/exit, volume and price where published | Month/point/country | EIA Natural Gas / API v2 | Current Natural Gas bulk history is preserved as the V1 floor. Publication/revision vintages remain incomplete; high-frequency feedgas is Later. |
| V1 | Spot/reference price | Henry Hub spot price and publication timestamp | Day | EIA Natural Gas / API v2 | Current Natural Gas bulk history is preserved. Align to actual publication availability before backtest use rather than trade date alone. |
| V1 | Calendar/seasonality | session calendar, month/week/day-of-year, injection/withdrawal season, days-to-expiry | Session | Massive schedules + CME definitions + derived | Massive schedule capture is implemented in bounded windows and preserves source calendar events locally. Derived calendar versioning is required; canonical use remains subject to the Massive licensing gate. |
| Later | CFTC positioning | producer/merchant, swap dealer, Managed Money and other positions; net, change, % OI, rolling percentile/z-score | Week | CFTC COT, NYMEX code `023651` | Public. Use actual Friday release/holiday calendar; report date is not availability date. |
| Later | Drilling and supply response | rig count, wells drilled/completed, DUCs, new-well productivity, basin activity, producer capex where reproducible | Week/month | EIA STEO/DPR + Baker Hughes | Secondary/slow-moving; preserve report vintage because productivity/DUC estimates can be revised. |
| Later | Gulf tropical disruption | issued storm track/intensity/advisories, landfall risk, platform/rig evacuation, offshore gas shut-in MMCF/d and % | Advisory/day/event | NOAA NHC + BSEE | Use issued advisories for forecasts; BSEE shut-in estimates are event reports and should retain publication time. |
| Later | Expectations and forecast revisions | EIA STEO production/demand/LNG/storage forecasts, revision deltas; storage consensus if a licensed historical survey is approved | Forecast vintage/period | EIA STEO + licensed consensus candidate | Preserve each forecast vintage. Market-consensus history is a licensing/data-quality decision, not assumed available. |
| Later | Macro/industrial demand | industrial production, manufacturing activity, GDP, employment and sector output | Month/quarter | Federal Reserve, BEA, BLS | Slow-moving regime/demand features; use actual release timestamps and vintages where revisions occur. |
| Later | Pipelines, outages and LNG feedgas | physical flow, nominations, capacity, maintenance, force majeure, terminal feedgas/utilisation | Hour/day/asset | Pipeline EBBs; commercial aggregator candidate | No single verified free historical vintage feed. Prefer captured public notices or an explicitly approved commercial source. |
| Later | Options and volatility surface | IV, skew, term structure, volume/OI by strike/expiry, event-implied volatility | Contract/strike/day | CME / licensed market-data vendor | Historical licensing/access decision required. |
| Later | Substitution/cross-asset | WTI, coal, power prices, spark/dark spreads, nuclear outages, renewables | Hour/day | EIA, CME and power-market sources | Add only through pre-registered economic hypotheses. |

## 2. Global / Interconnect

This layer represents transmission between regional gas markets: LNG, European pipeline flows, storage, weather, power and benchmark spreads. It supports eventual Henry Hub-TTF-JKM cross-market research without treating gas as one globally uniform price.

| Priority | Data family | Ideal datapoints | Grain | Preferred source | Access / point-in-time note |
|---|---|---|---|---|---|
| V1 | TTF market and curve | per-expiry price/settlement, volume/OI if licensed, expiry; M1-M12 spreads, seasonal strips, slope/curvature | Contract/day | ICE Dutch TTF futures | Official contract source; historical market-data entitlement/licensing must be verified before ingestion. |
| V1 | Cross-market FX | EUR/USD; GBP/EUR if NBP is added; FX-normalised HH-TTF spreads | Day | ECB Data Portal | Public API. Daily reference rates are published around 16:00 CET; use market FX later if intraday timing matters. |
| V1 | European gas transmission | physical flow, direction, nominations where published, technical/available capacity, interconnection point, corridor | Hour/day/point | ENTSOG Transparency Platform | Public transparency data. Preserve publication timestamps and corrections. |
| V1 | European storage | stock, injection, withdrawal, working capacity, fill %, available/contracted capacity, outages | Day/facility/country | GIE AGSI | Free registration/API key; daily data. Snapshot revisions and changing facility/EIC metadata. |
| V1 | European LNG terminals | LNG inventory, send-out, receipts where available, regas capacity/utilisation, available capacity, maintenance/outages | Day/facility | GIE ALSI | Free registration/API key; daily data. Preserve facility identity and revisions. |
| V1 | European issued weather forecasts | issue/valid/available time, temperature, HDD/CDD, wind, solar-related weather, forecast revisions by demand region | Forecast run/hour | Open-Meteo archived issued runs; NOAA global models | Use issued forecasts only. Weight by population/gas demand and retain forecast vintage. |
| V1 | European electricity system | actual/forecast load, generation by fuel, wind/solar forecast, hydro storage, outages, cross-border flow, day-ahead power price | 15-min/hour/day/bidding zone | ENTSO-E Transparency Platform | Public API/token workflow. Keep source publication/revision state. |
| V1 | Gas/LNG inside information | planned/unplanned outage, unavailable capacity, start/end, asset, affected quantity and update history | Event/asset | GIE IIP, ENTSOG/TSO notices, ACER REMIT sources | Event timestamps are features; retain every update rather than only final outage state. |
| Later | Global gas balance | production, LNG/pipeline imports/exports, stock change, inland demand, power/heat gas use by country | Month/country | JODI-Gas | Public global structural/regime layer; updated monthly and subject to country revisions. |
| Later | JKM / Asian LNG benchmark | JKM futures/assessment proxy, curve, spreads to TTF and Henry Hub | Contract/day | CME JKM; Platts/licensed source if adopted | Benchmark methodology/price history is licensed; entitlement decision required. |
| Later | LNG cargo and vessel flows | vessel, cargo size, load/discharge terminal, origin/destination, ETA, diversion, floating storage | Cargo/event | Kpler or equivalent commercial provider | High-value but commercial. Acquire only after cost/licensing review. |
| Later | LNG freight and shipping constraints | route freight rate, vessel availability, boil-off assumptions, canal/transit disruption | Day/route | Baltic/Clarksons/S&P/Argus candidates | Commercial/mixed access; source decision required. |
| Later | Detailed EU gas trade | import/export quantity and value by product, partner country and mode | Month/country | Eurostat Comext | Free API/bulk. Latest database is revised rather than vintage-versioned; snapshot extracts. |
| Later | EU gas trading structure | spot/long-term/bilateral/LNG transaction counts, volumes and participant activity | Quarter/market | ACER REMIT Data Reference Centre | Public aggregated downloads; useful for regime/liquidity research, not daily prediction. |
| Later | Carbon and coal switching | EUA price, coal price, clean dark/spark economics | Day | ICE/EEX/licensed market sources | Add when fuel-switch hypotheses justify licensing effort. |

## 3. Norway / Europe

This layer is the planned supply-side foundation for a later TTF/European model. It reuses TTF, European storage, weather, power and LNG data from the Global/Interconnect layer rather than duplicating them.

| Priority | Data family | Ideal datapoints | Grain | Preferred source | Access / point-in-time note |
|---|---|---|---|---|---|
| V1 | NCS gas production | field, NPDID information carrier, net saleable gas, gross gas, NCS total; revision/update timestamp | Month/field | Norwegian Offshore Directorate FactPages | Public CSV/XML/Excel. Snapshot monthly releases because published history can be revised. |
| V1 | Norwegian gas transport | nominations/flow where public, receiving terminal, destination corridor, capacity and utilisation | Hour/day/point | Gassco + ENTSOG | Gassco is operational authority; use ENTSOG point data for machine-readable cross-border flow where available. |
| V1 | Norwegian maintenance/outages | planned/unplanned event, asset/field, unavailable capacity, start/end, update/cancellation history | Event/asset | Gassco FLOW/UMM | Public market messages. Preserve every publication/update timestamp; machine-access/history depth must be verified. |
| V1 | Gas exports | gaseous natural-gas export volume (Sm3), NOK value, partner country; derived unit value and destination mix | Month/country | SSB tables `08864` and `08799` via PxWebApi v2 | Public, no registration, CC BY 4.0. SSB revises history; archive extracts by release. |
| V1 | NOK FX | EUR/NOK, USD/NOK and publication timestamp | Day | Norges Bank open data API | Public. Daily reference rates are published about 16:00 CET; respect availability. |
| Later | Norwegian power and hydro | production/consumption, import/export, bidding-zone price, reservoir fill, inflow, snow/hydrological balance | 15-min/hour/week/zone | ENTSO-E, Statnett, NVE | Public. NVE reservoir data are weekly; some Statnett series originate from ENTSO-E. |
| Later | Norwegian weather | observations for verification; issued temperature/wind/precipitation forecasts captured going forward | Hour/station/grid | MET Norway APIs; archived issued forecasts from Open-Meteo/NOAA | MET observations are truth data, not a substitute for historical forecast vintages. |
| Later | Upstream capacity and resources | reserves/resources, field status, facilities, wellbores, discoveries, production profiles | Field/well/event | Norwegian Offshore Directorate | Public FactPages; structural/regime features rather than short-horizon signals. |
| Later | Investment and drilling | petroleum investment, exploration/development spending, wells/activity | Quarter/month | SSB + Norwegian Offshore Directorate | Slow-moving supply-capacity features; publication/revision timestamps required. |
| Later | Norwegian macro/export transmission | petroleum revenue, trade balance, industrial activity, Norges Bank petroleum FX transactions | Month/quarter | SSB + Norges Bank | Primarily explanatory/regime variables; avoid using outcomes that merely restate gas-price moves. |
| Later | Operator forward export estimates | field-level future gas export expectations | Forecast vintage/field | Gassco GMDC candidate | Data exist operationally, but public historical machine access is not established; source eligibility unresolved. |

## Source register

Candidate status here does not constitute third-party approval. Approval and implementation state remain governed by [`docs/THIRD_PARTY.md`](THIRD_PARTY.md) and [`config/data_sources.json`](../config/data_sources.json).

| ID | Source | Access | Primary use |
|---|---|---|---|
| US-MKT | [Massive Futures](https://massive.com/docs/rest/futures) + [CME Henry Hub](https://www.cmegroup.com/markets/energy/natural-gas/natural-gas.html) | Massive API key; CME public specifications | Henry Hub contracts, prices, expiry/market definition |
| US-EIA | [EIA Open Data API](https://www.eia.gov/opendata/) | Free API key + public Natural Gas bulk ZIP | Storage, production, demand, imports/exports, spot, EIA-930 power |
| US-CFTC | [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | Public | Henry Hub positioning; code `023651` |
| US-SUPPLY | [EIA STEO/DPR](https://www.eia.gov/petroleum/drilling/) + [Baker Hughes Rig Count](https://rigcount.bakerhughes.com/na-rig-count) | Public | Rigs, drilling, DUCs and production-productivity estimates |
| US-STORM | [NOAA NHC Data Archive](https://www.nhc.noaa.gov/data/) + [BSEE](https://www.bsee.gov/) | Public | Issued tropical advisories and offshore shut-in/evacuation reports |
| US-MACRO | [Federal Reserve Economic Data](https://fred.stlouisfed.org/) + [BEA](https://www.bea.gov/data) + [BLS](https://www.bls.gov/data/) | Public | Industrial and macro demand/regime data |
| WX-ARCHIVE | [Open-Meteo](https://open-meteo.com/en/docs) + [NOAA GFS](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast) | Public | Actually-issued forecast vintages; Single Runs adapter implemented |
| EU-TTF | [ICE Dutch TTF Natural Gas Futures](https://www.ice.com/products/82843860/ICE-Futures-Europe-Dutch-TTF-Natural-Gas-Futures) | Contract specs public; historical market data subject to entitlement | TTF market/curve |
| EU-FX | [ECB Data Portal](https://data.ecb.europa.eu/key-figures/ecb-interest-rates-and-exchange-rates/exchange-rates) | Public API | EUR/USD and other cross-market reference FX |
| EU-FLOW | [ENTSOG Transparency](https://www.entsog.eu/transparency-activities) | Public | European gas flows/capacities |
| EU-GIE | [GIE AGSI/ALSI](https://www.gie.eu/agsi-and-alsi-transparency-platforms/) | Free registration/API key | Storage and LNG terminals |
| EU-IIP | [GIE Inside Information Platform](https://iip.gie.eu/) | Public | Planned/unplanned gas storage/LNG inside information |
| EU-PWR | [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) | Public registration/API token | Load, generation, renewables, hydro, outages, power prices |
| EU-REMIT | [ACER REMIT Data Reference Centre](https://www.acer.europa.eu/market-transparency/remit-data-reference-centre) | Public aggregated downloads | Gas/LNG trading structure and REMIT research data |
| GLOBAL-JODI | [JODI-Gas World Database](https://www.jodidata.org/gas/database/overview.aspx) | Public | Monthly global production, trade, stocks and demand |
| GLOBAL-JKM | [CME LNG Japan/Korea Marker](https://www.cmegroup.com/markets/energy/natural-gas/lng-japan-korea-marker-platts-swap.calendar.html) | Contract metadata public; benchmark/history licensing to verify | JKM curve and TTF/HH spreads |
| EU-TRADE | [Eurostat Comext](https://ec.europa.eu/eurostat/web/international-trade-in-goods/database) | Free API/bulk | Detailed monthly gas trade by partner/product |
| GLOBAL-LNG | [Kpler LNG](https://www.kpler.com/) or equivalent | Commercial candidate | Cargo/vessel/freight/pipeline intelligence |
| NO-PROD | [Norwegian Offshore Directorate FactPages](https://factpages.sodir.no/en/field/tableview/production/saleable/monthly) | Public CSV/XML/Excel | Field-level and total NCS production |
| NO-FLOW | [Gassco](https://www.gassco.no/en/) + [Gassco FLOW/UMM](https://umm.gassco.no/) | Public web; machine access to verify | Norwegian transport, maintenance and outages |
| NO-SSB | [SSB PxWebApi v2](https://www.ssb.no/en/api/pxwebapi) | Public, no registration, CC BY 4.0 | Exports/economy; tables `08864`, `08799` |
| NO-PWR | [Statnett power-system data](https://www.statnett.no/en/for-stakeholders-in-the-power-industry/data-from-the-power-system/) + [NVE reservoir statistics](https://api.nve.no/doc/magasinstatistikk/) | Public | Norwegian power, exchange and hydro state |
| NO-WX | [MET Norway Weather API](https://api.met.no/) | Public with service terms | Norwegian observation/current forecast support |
| NO-FX | [Norges Bank exchange rates](https://www.norges-bank.no/en/topics/Statistics/exchange_rates/?tab=api) | Public API | EUR/NOK, USD/NOK and other reference FX |

## Acquisition order

1. Resolve Massive non-display/backtesting entitlement; retain the resumable M1-M12 local archive and verified roll contract.
2. Extend the U.S. V1 point-in-time layer by reconstructing original/revised vintages for WNGSR/EIA-930 and historical publication/revision state for monthly EIA fundamentals, while expanding the demand-region issued-weather archive. The current layer supports explicit screening and weather `research_pit`; it does not unlock canonical evidence for revised EIA histories.
3. Add the Global/Interconnect V1 layer: TTF, ENTSOG, AGSI/ALSI, European weather/power and outage messages.
4. Build the Norway/Europe V1 layer: NCS production, Gassco flows/outages, SSB exports and NOK FX.
5. Add Later sources only when ablation tests or a pre-registered hypothesis justify their acquisition or licensing cost.

The manifest should be updated when a source is proven unusable, a materially better authoritative source is identified, or a data family is promoted into active implementation. Operational status changes belong in `config/data_sources.json`, not here.
