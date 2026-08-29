# Data Architecture

This document owns the desired dataset families and acquisition architecture. It does not own current provider status, availability flags, or evidence gates; those live in `config/data_sources.json`. Approval and licensing boundaries live in `docs/THIRD_PARTY.md`.

## Data contract

Time-varying inputs should preserve the time the observation describes, when it was issued or published, when it became available to the strategy, when it was retrieved, source/version identity, units, and revision state where applicable. Backtests may use information only after it was knowable. Revised historical values must not silently replace the value available at the prediction time.

Raw source values should remain reproducible and versioned. Derived features are transformations, not new sources. A present-day historical snapshot is not point-in-time evidence unless historical publication and revision availability are also known.

## Core data families

| Family | Examples | Purpose |
| --- | --- | --- |
| Market structure | Per-contract prices, settlement, volume/OI, expiry, curve and roll state | Tradable market truth and futures structure |
| Weather | Issued forecasts and revisions by demand region | Demand and event expectations |
| Fundamentals | Storage, production, consumption, LNG, pipeline flows, power burn | Physical balance and surprises |
| Positioning | CFTC and equivalent participant positioning | Crowding and market structure |
| Volatility/options | Realized volatility, implied volatility, skew and term structure where licensed | Risk and uncertainty |
| Cross-market | Power, oil, coal, FX, regional gas benchmarks and transport links | Substitution and transmission |
| Events | Outages, storms, maintenance, releases and known event timing | Discrete shocks and regime context |
| Macro/structural | Industrial activity, drilling, investment and capacity | Slow-moving regime context |

## Geographic progression

**U.S. / Henry Hub** is the first full reference market and establishes the complete data, point-in-time, research and execution interfaces.

**Global / interconnect** data adds transmission between regional gas markets: LNG, European flows/storage, weather, power, FX and benchmark spreads. These inputs are admitted only when a governed hypothesis justifies them.

**Norway / Europe** is a later supply-side and regional-market layer built on the same interfaces, using Norwegian production/transport/outage data together with European gas and power data.
Other instruments should reuse the core data contract and provider interfaces, adding only instrument-specific metadata, fundamentals, calendars and source mappings.

## Acquisition principles

1. Prefer authoritative, reproducible sources and retain raw provenance.
2. Prove point-in-time admissibility before promoting a source into serious backtests.
3. Keep providers replaceable behind stable interfaces.
4. Acquire expensive or difficult data only when a preregistered hypothesis or measured gap justifies it.
5. Treat each new instrument as an independent empirical programme rather than assuming Henry Hub findings transfer.

Current source choices and readiness belong in `config/data_sources.json`; source approval and licensing belong in `docs/THIRD_PARTY.md`.