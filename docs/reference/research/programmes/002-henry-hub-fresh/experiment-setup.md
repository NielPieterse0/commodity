<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/experiment-setup.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/experiment-setup.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `status` | non_outcome_feasibility_complete_unfrozen |
| `feasibility_authority_ref` | evidence-map.json |
| `supporting_feasibility_detail_ref` | feasibility-ledger.json |
| `source_feasibility_scan_ref` | .work/changes/289-l0-l3-henry-hub-research/feasibility-scan.json |
| `next_action` | All prior REDESIGN defects are resolved in design. Implement/verify the fourteen GO routes; seven HOLD routes remain blocked. No empirical literature-result execution or freeze transition is authorized. |
| `implementation_contracts_ref` | implementation-contracts.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `status` | str |
| `authority` | object (3 keys) |
| `feasibility_authority_ref` | str |
| `supporting_feasibility_detail_ref` | str |
| `source_feasibility_scan_ref` | str |
| `canonical_inputs` | object (8 keys) |
| `missing_or_unproven_inputs` | array (5 items) |
| `design_readiness` | array (21 items) |
| `feasibility_protocol` | object (3 keys) |
| `feasibility_summary` | object (5 keys) |
| `post_feasibility_work_order` | array (4 items) |
| `next_action` | str |
| `implementation_contracts_ref` | str |
| `implementation_status` | object (4 keys) |
