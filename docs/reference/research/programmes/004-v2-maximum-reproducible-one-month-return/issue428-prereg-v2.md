<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-prereg-v2.json -->

# 004-v2-maximum-reproducible-one-month-return

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-prereg-v2.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 2 |
| `issue` | 428 |
| `programme_id` | 004-v2-maximum-reproducible-one-month-return |
| `status` | frozen_before_issue428_scoring |
| `supersedes` | issue428-prereg-v1.json |
| `supersession_reason` | Before any #428 scoring, implementation mapping proved that the six inherited #427/#448 retained signal representations do not have nested-selection support for the originally listed 2015-2016 policy score years. V2 therefore starts rolling policy diagnostics only where the inherited selection chain is supportable, while preserving the same outer evaluations, candidate budget, evidence wall, and promotion gate. |
| `scientific_role` | L3_preregistration |
| `claim_boundary` | adaptive_development_only_no_confirmation_claim |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_id` | str |
| `status` | str |
| `supersedes` | str |
| `supersession_reason` | str |
| `scientific_role` | str |
| `claim_boundary` | str |
| `evidence_boundary` | object (4 keys) |
| `upstream_evidence` | object (9 keys) |
| `frozen_handoff` | object (5 keys) |
| `chronology` | object (9 keys) |
| `signal_state_contract` | object (5 keys) |
| `regime_contract` | object (6 keys) |
| `confidence_contract` | object (8 keys) |
| `candidate_grid` | object (12 keys) |
| `meta_features` | object (2 keys) |
| `open_interest_lane` | object (6 keys) |
| `selection` | object (3 keys) |
| `effective_sample_controls` | object (4 keys) |
| `required_diagnostics` | array (15 items) |
| `promotion_gate` | object (6 keys) |
| `budgets` | object (4 keys) |
| `complexity_control` | object (3 keys) |
