<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json -->

# 004-v2-maximum-reproducible-one-month-return

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 004-v2-maximum-reproducible-one-month-return |
| `research_line_id` | 001-v2-optimization-execution |
| `status` | active |
| `big_picture` | Execute Programme #393 as a chronological, auditable optimization campaign for reproducible one-month net trading return. The current pre-freeze problem is to replace history-wide fixed parameter selection with a causal adaptive procedure that can choose experts, horizons, sizing, position actions and execution behavior from point-in-time state. |
| `why_zoomed_in` | Issues #459/#429/#430/#431 established that V2 contains material but conditional and time-sensitive development value: joint side-specific policy gains, state-dependent sizing, fast adaptation value, and strong execution-latency sensitivity. #465 therefore becomes the final broad discovery stage before #414 champion simplification and freeze. |
| `tested_role_target_horizon` | Completed development work through #431 tested joint signal/side/regime policies, lifecycle/position structure, sizing/risk, and execution/adaptation over chronological pre-2023 outers. #465 will test a point-in-time time-instance representation and causal adaptive whole-system controller without accessing protected confirmation. |
| `revisit_trigger` | Return to upstream research design if #465 cannot reconstruct a candidate field at its true availability timestamp, if an alternative role is not scientifically distinct from a prior negative, or if adaptive selection requires protected outcomes or future-derived diagnostics. |
| `programme_interpretation` | V2 development has moved from isolated family optimization to whole-system causal adaptation. The next scientific object is not one fixed fifteen-year parameter vector but a frozen procedure that selects bounded parameters and actions from information available at each timestamp; #414 remains the simplification/freeze gate after #465. |
| `selection_basis` | Primary objective remains chronological net percentage return after realistic costs. #465 may search aggressively, but every model, parameter, weight, memory, threshold and action must be selected from prior/inner evidence only and must satisfy minimum executability, sample, concentration, drawdown and stability constraints before #414 can freeze it. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `zoom_level` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `legacy_research_line_ids` | array (0 items) |
| `status` | str |
| `big_picture` | str |
| `why_zoomed_in` | str |
| `tested_role_target_horizon` | str |
| `historical_facts` | object (3 keys) |
| `useful_secondary_observations` | array (4 items) |
| `remaining_untested_roles` | array (8 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (8 items) |
| `experiment_history` | array (5 items) |
| `experiment_refs` | array (0 items) |
| `selection_basis` | str |
| `stopping_rules` | object (1 keys) |
