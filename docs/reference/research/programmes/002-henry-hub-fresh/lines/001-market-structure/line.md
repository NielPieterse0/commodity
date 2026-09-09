<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/001-market-structure/line.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/001-market-structure/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 001-market-structure |
| `status` | selected |
| `selection_basis` | external_evidence |
| `big_picture` | This line tests maturity and seasonal curve structure as part of the wider goal of understanding Henry Hub before prediction or model selection. |
| `why_zoomed_in` | Exact-contract market structure is the cleanest calibration layer for testing whether canonical Henry Hub market data preserve published stylized facts. |
| `tested_role_target_horizon` | rep-001 and rep-002 are selected for exact preregistration/freeze; no Programme 002 market outcome has been opened yet. |
| `revisit_trigger` | Revisit empirical execution only after applicable HOLD/REDESIGN blockers are resolved, implementation/power contracts are verified, and the operator explicitly authorizes the transition. |
| `programme_interpretation` | This line remains pre-empirical. Literature support is external evidence, not an internal programme result. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `zoom_level` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `legacy_research_line_ids` | array (0 items) |
| `status` | str |
| `selection_basis` | str |
| `stopping_rules` | object (7 keys) |
| `big_picture` | str |
| `why_zoomed_in` | str |
| `tested_role_target_horizon` | str |
| `historical_facts` | object (3 keys) |
| `useful_secondary_observations` | array (2 items) |
| `remaining_untested_roles` | array (2 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (4 items) |
| `experiment_history` | array (0 items) |
| `experiment_refs` | array (0 items) |
