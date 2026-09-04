<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/research-synthesis.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/research-synthesis.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `scientific_start_state` | clean_slate |
| `internal_reproductions_completed` | 0 |
| `design_authority` | experiment-designs.json |
| `setup_authority` | experiment-setup.json |
| `scientific_design_state` | all_redesign_defects_resolved_non_outcome_implementation_stage_unfrozen |
| `feasibility_authority_ref` | evidence-map.json |
| `supporting_feasibility_detail_ref` | feasibility-ledger.json |
| `interpretation_rule` | External literature support is not internal proof. A finding becomes programme-reproduced only after a fresh programme experiment reproduces it under the declared design, source fidelity, MEPI/power and semantic rules. Contextual sources and exploratory gap discovery cannot be counted as strict reproduction. |
| `next_stage` | Implement and verify the fourteen GO design constructions without empirical literature-result execution. Seven HOLD designs remain governed by revisit-triggers.json; all empirical/freeze/protected-evidence transitions remain operator-gated. |
| `implementation_contracts_ref` | implementation-contracts.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `scientific_start_state` | str |
| `internal_reproductions_completed` | int |
| `literature_findings` | object (8 keys) |
| `design_authority` | str |
| `setup_authority` | str |
| `design_coverage` | object (4 keys) |
| `scientific_design_state` | str |
| `feasibility_authority_ref` | str |
| `supporting_feasibility_detail_ref` | str |
| `feasibility_summary` | object (4 keys) |
| `interpretation_rule` | str |
| `next_stage` | str |
| `implementation_contracts_ref` | str |
| `implementation_status` | object (4 keys) |
