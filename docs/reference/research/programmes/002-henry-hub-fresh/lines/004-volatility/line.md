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
| `tested_role_target_horizon` | Phase 1 evaluated rep-009 through the frozen pre-scoring uncertainty-capacity gate. Its 108 research-OOS sessions at block size 20 provide 5.4 effective blocks versus 8 required, so no forecast scoring or protected-confirmation access occurred. |
| `revisit_trigger` | Phase 1 is closed. Revisit or extend this line only through a new explicitly authorized successor research scope; do not tune against the same research-OOS evidence to rescue a held or inconclusive result. |
| `programme_interpretation` | Line 004 has a completed Phase-1 capacity result for rep-009 but no scored forecast result and no Phase-2 survivor. |

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
| `useful_secondary_observations` | array (3 items) |
| `remaining_untested_roles` | array (2 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (6 items) |
| `experiment_history` | array (1 items) |
| `experiment_refs` | array (1 items) |
