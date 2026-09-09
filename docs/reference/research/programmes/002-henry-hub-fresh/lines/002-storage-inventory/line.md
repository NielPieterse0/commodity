<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/002-storage-inventory/line.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/002-storage-inventory/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 002-storage-inventory |
| `status` | active |
| `selection_basis` | Fresh external-literature mapping under programme 002; no legacy internal result is used as scientific calibration or expected outcome. |
| `big_picture` | This line tests storage state, scarcity and forward-curve relations as part of the wider goal of understanding Henry Hub before prediction or model selection. |
| `why_zoomed_in` | Storage is a central physical state variable in the Henry Hub literature, but revised-history descriptive reproduction must remain separate from PIT event/predictive use. |
| `tested_role_target_horizon` | Phase 1 evaluated rep-004 and rep-005 under the frozen forecast contract. Both stopped at the pre-scoring uncertainty-capacity gate with 28 research-OOS rows and 7 effective blocks versus 8 required. Separately, rep-005 reproduced the Geman-Ohana source-period scarcity-volatility pattern; the 2010-2026 extension reversed sign. |
| `revisit_trigger` | Phase 1 is closed. Revisit or extend this line only through a new explicitly authorized successor research scope; do not tune against the same research-OOS evidence to rescue a held or inconclusive result. |
| `programme_interpretation` | Line 002 now distinguishes a successful historical rep-005 reproduction from modern regime reversal and capacity-limited forecast translations. No Phase-2 survivor emerged. |

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
| `useful_secondary_observations` | array (4 items) |
| `remaining_untested_roles` | array (2 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (8 items) |
| `experiment_history` | array (2 items) |
| `experiment_refs` | array (2 items) |
