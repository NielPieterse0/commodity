<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/rep-002-seasonal-forward-curve/literature-reproduction.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/rep-002-seasonal-forward-curve/literature-reproduction.json`

## Overview

| Field | Value |
| --- | --- |
| `design_id` | rep-002-seasonal-forward-curve |
| `interpretation` | The Mirantes exact convenience-yield replication remains unavailable because the source zero-coupon rate contract is unresolved. The project therefore reports the exact futures-price test and the adjacent-month futures-ratio component separately without inventing an interest-rate term. |
| `issue` | 327 |
| `literature_disposition` | CARRY_PATTERN_REPRODUCED_EXACT_CONVENIENCE_YIELD_RATE_SOURCE_UNAVAILABLE |
| `literature_gate_closed` | true |
| `market_cache_sha256` | cedc888c9758ad817c1b3742cc5aac323bcd8b6924f58b6380b421661fe953e4 |
| `market_history_start` | 2010-06-04T00:00:00+00:00 |
| `programme_id` | 002-henry-hub-fresh |
| `protected_confirmation_accessed` | false |
| `replication_class_achieved` | near_replication_futures_ratio_component |
| `replication_class_target` | near_replication |
| `research_cutoff_exclusive` | 2023-05-09T00:00:00+00:00 |
| `schema_version` | 1 |

## Structure

| Field | Shape |
| --- | --- |
| `design_id` | str |
| `interpretation` | str |
| `issue` | int |
| `literature_disposition` | str |
| `literature_gate_closed` | bool |
| `market_cache_sha256` | str |
| `market_history_start` | str |
| `partial_source_period_overlap` | object (7 keys) |
| `programme_id` | str |
| `project_sample` | object (7 keys) |
| `protected_confirmation_accessed` | bool |
| `replication_class_achieved` | str |
| `replication_class_target` | str |
| `research_cutoff_exclusive` | str |
| `schema_version` | int |
| `sealed_confirmation` | object (4 keys) |
| `source_contract` | object (2 keys) |
| `source_fidelity` | object (5 keys) |
