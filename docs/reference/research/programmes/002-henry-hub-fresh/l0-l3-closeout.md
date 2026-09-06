<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/l0-l3-closeout.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/l0-l3-closeout.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `closed_scope` | original Henry Hub literature-replication research cycle through L0-L3 design, source feasibility and pre-outcome implementation readiness |
| `status` | closed_transferred_to_forecast_proof |
| `scientific_history_inherited` | false |
| `internal_reproductions_completed` | 0 |
| `empirical_execution_authority` | false |
| `reopen_reason` | The initial candidate designs were not execution-quality: they did not fully specify estimands, H0/H1, disconfirmers, PIT semantics, multiplicity, MEPI/power gates, or source-readiness failure conditions for every literature finding. |
| `scientific_boundary` | All mapped findings remain external literature findings until newly reproduced inside this programme. Contextual evidence and exploratory literature gaps cannot be promoted as strict reproductions. |
| `next_stage` | Start Phase 1 from research-synthesis.json#phase_0_transition. Pre-proof empirical work uses governed schema-v3 exploratory runs on development and rolling research-OOS data. Exact paid-data replications are non-critical; reserved/sealed confirmation remains preregistration/freeze-gated. |
| `implementation_contracts_ref` | implementation-contracts.json |
| `phase_0_handoff_ref` | research-synthesis.json#phase_0_transition |

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
| `phase_0_handoff_ref` | str |
