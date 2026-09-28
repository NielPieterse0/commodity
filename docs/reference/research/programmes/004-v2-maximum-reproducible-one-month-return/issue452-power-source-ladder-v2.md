<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-power-source-ladder-v2.json -->

# Issue452 Power Source Ladder V2

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-power-source-ladder-v2.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 452 |
| `programme_issue` | 393 |
| `contract_id` | issue452-power-source-ladder-v2 |
| `status` | preregistered_before_power_rescoring |
| `supersedes` | issue452-power-source-ladder-v1 |
| `supersession_reason` | Pre-scoring source-feasibility work found a continuous MISO issued-load-forecast archive spanning the full development interval; adding it before ISO-NE avoids stitching different ISO-NE products while preserving the same U.S.-ISO power-demand hypothesis. |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `protected_confirmation_accessed` | false |
| `power_performance_scored_before_supersession` | false |
| `family` | power |
| `economic_hypothesis` | issued_us_iso_electricity_load_forecasts_as_power_burn_demand_information |
| `equivalence_rule` | A replacement must remain a U.S. ISO actually-issued electricity-load forecast and preserve the original power-demand mechanism; Norway/Europe must not be relabeled as this family. |
| `family_hold_rule` | Do not declare the power information family unavailable while a higher-priority equivalent source remains unaudited. |
| `scoring_rule` | Reuse the existing issue426 power roles, matched market-only controls, chronological blocks, 25-hour max staleness, search budget, and development cutoff unchanged for source-identifiable representations only. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `contract_id` | str |
| `status` | str |
| `supersedes` | str |
| `supersession_reason` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `protected_confirmation_accessed` | bool |
| `power_performance_scored_before_supersession` | bool |
| `family` | str |
| `economic_hypothesis` | str |
| `source_ladder` | array (4 items) |
| `equivalence_rule` | str |
| `miso_gate` | object (14 keys) |
| `representation_rule` | object (4 keys) |
| `family_hold_rule` | str |
| `scoring_rule` | str |
| `segregated_follow_on` | object (3 keys) |
| `failure_ladder` | array (6 items) |
