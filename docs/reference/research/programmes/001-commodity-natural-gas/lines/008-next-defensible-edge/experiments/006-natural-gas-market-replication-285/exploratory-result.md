<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/experiments/006-natural-gas-market-replication-285/exploratory-result.json -->

# commodity-ng

Source: `research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/experiments/006-natural-gas-market-replication-285/exploratory-result.json`

## Overview

| Field | Value |
| --- | --- |
| `gap` | The programme owns deep NG.FUT history, but had not yet shown that its long-history contract mapping and OHLCV semantics can reproduce well-established Henry Hub maturity-volatility and seasonal curve structure. |
| `mechanism` | Nearer Henry Hub futures should vary more as expiry approaches because new information has less time to be absorbed across storage/production adjustments, while weather-driven demand and storage economics create a repeatable winter-versus-injection seasonal forward-curve pattern. |
| `programme_conclusion` | REPLICATED as exploratory development evidence. The 2010+ Databento pipeline reproduces two literature-supported Henry Hub market structures under honest OHLCV-close semantics. Rank Samuelson maturity-volatility first because it is directly defined, strong, monotone and cross-source-era robust; rank seasonal curve structure second because it is also directionally replicated but has more construction choices. Do not treat either as independent confirmation. |
| `programme_id` | commodity-ng |
| `promotion_decision` | continue |
| `research_line_id` | line-next-defensible-edge |
| `run_id` | natural-gas-market-replication-285 |
| `schema_version` | 2 |

## Structure

| Field | Shape |
| --- | --- |
| `comparison` | object (2 keys) |
| `execution` | object (6 keys) |
| `expectations` | object (2 keys) |
| `external_triangulation` | object (2 keys) |
| `feasibility` | object (2 keys) |
| `gap` | str |
| `hypotheses` | object (2 keys) |
| `lifecycle` | array (15 items) |
| `lineage` | object (2 keys) |
| `literature_snapshot_ref` | object (2 keys) |
| `mechanism` | str |
| `orientation` | object (4 keys) |
| `programme_conclusion` | str |
| `programme_id` | str |
| `promotion_decision` | str |
| `research_line_id` | str |
| `revisit_triggers` | array (1 items) |
| `run_id` | str |
| `schema_version` | int |
| `verification` | object (2 keys) |
| `zoom_in` | object (2 keys) |
