<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/004-volatility/line.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/004-volatility/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 004-volatility |
| `status` | active |
| `selection_basis` | Fresh external-literature mapping under programme 002; no legacy internal result is used as scientific calibration or expected outcome. |
| `big_picture` | This line tests announcement and state-dependent volatility as part of the wider goal of understanding Henry Hub before prediction or model selection. |
| `why_zoomed_in` | Volatility is a downstream market response that should be decomposed by source-faithful state families before any predictive model is selected. |
| `tested_role_target_horizon` | No literature outcome has been tested in programme 002. Current evidence covers literature mapping, source semantics, source capacity, dependence and feasibility only. |
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
| `stopping_rules` | object (2 keys) |
| `big_picture` | str |
| `why_zoomed_in` | str |
| `tested_role_target_horizon` | str |
| `historical_facts` | object (3 keys) |
| `useful_secondary_observations` | array (3 items) |
| `remaining_untested_roles` | array (3 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (4 items) |
| `experiment_history` | array (0 items) |
| `experiment_refs` | array (0 items) |
