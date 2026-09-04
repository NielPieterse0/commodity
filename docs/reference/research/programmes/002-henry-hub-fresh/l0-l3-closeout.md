<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/l0-l3-closeout.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/l0-l3-closeout.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `closed_scope` | historical L0-L3 literature research and initial reproduction-design mapping |
| `status` | reopened_design_feasibility_and_redesign_resolution_complete_unfrozen |
| `scientific_history_inherited` | false |
| `internal_reproductions_completed` | 0 |
| `empirical_execution_authority` | false |
| `reopen_reason` | The initial candidate designs were not execution-quality: they did not fully specify estimands, H0/H1, disconfirmers, PIT semantics, multiplicity, MEPI/power gates, or source-readiness failure conditions for every literature finding. |
| `scientific_boundary` | All mapped findings remain external literature findings until newly reproduced inside this programme. Contextual evidence and exploratory literature gaps cannot be promoted as strict reproductions. |
| `next_stage` | Implement/verify GO machinery and resolve HOLD triggers only. No empirical literature-result execution, protected-evidence opening, preregistration, sealing or confirmation is authorized. |
| `implementation_contracts_ref` | implementation-contracts.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `closed_scope` | str |
| `status` | str |
| `scientific_history_inherited` | bool |
| `internal_reproductions_completed` | int |
| `empirical_execution_authority` | bool |
| `prior_counts` | object (5 keys) |
| `reopen_reason` | str |
| `current_design_refs` | array (4 items) |
| `source_library_recovery` | object (7 keys) |
| `source_hunt_progress` | object (7 keys) |
| `feasibility` | object (6 keys) |
| `current_integrity` | object (8 keys) |
| `scientific_boundary` | str |
| `next_stage` | str |
| `implementation_contracts_ref` | str |
| `implementation_status` | object (4 keys) |
