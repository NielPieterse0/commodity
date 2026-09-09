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
| `status` | active |
| `selection_basis` | Fresh external-literature mapping under programme 002; no legacy internal result is used as scientific calibration or expected outcome. |
| `big_picture` | This line tests maturity and seasonal curve structure as part of the wider goal of understanding Henry Hub before prediction or model selection. |
| `why_zoomed_in` | Exact-contract market structure is the cleanest calibration layer for testing whether canonical Henry Hub market data preserve published stylized facts. |
| `tested_role_target_horizon` | Phase 1 completed rep-001 and rep-002 literature accounting and separate chronological research-OOS forecast translations. rep-001 reproduced the core Samuelson maturity-volatility effect; rep-002 reproduced the source-faithful adjacent-month carry seasonality component. Both forecast translations were INCONCLUSIVE and neither met the 1% relative-RMSE SURVIVE threshold. |
| `revisit_trigger` | Phase 1 is closed. Revisit or extend this line only through a new explicitly authorized successor research scope; do not tune against the same research-OOS evidence to rescue a held or inconclusive result. |
| `programme_interpretation` | Line 001 contains successful literature accounting for rep-001 and rep-002 but no Phase-2 predictive survivor. Literature reproduction and forecast usefulness remain separate conclusions. |

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
| `stopping_rules` | object (3 keys) |
| `big_picture` | str |
| `why_zoomed_in` | str |
| `tested_role_target_horizon` | str |
| `historical_facts` | object (3 keys) |
| `useful_secondary_observations` | array (2 items) |
| `remaining_untested_roles` | array (0 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (9 items) |
| `experiment_history` | array (2 items) |
| `experiment_refs` | array (2 items) |
