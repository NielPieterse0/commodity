<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v3.json -->

# Issue426 Optimization Plan V3

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v3.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 426 |
| `programme_issue` | 393 |
| `plan_id` | issue426-optimization-plan-v3 |
| `status` | registered_before_authoritative_issue426_scoring |
| `supersedes` | issue426-optimization-plan-v2 |
| `supersession_reason` | implementation review found sizing and risk_modifier unidentifiable under the inherited single-contract fixed-risk replay and confidence needed distinct train-only weighting semantics |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `base_configuration` | issue425-result-v1.nested_outer[].search.selected_config matched by outer_block_id |
| `selection_rule` | select_only_on_strictly_prior_inner_blocks_then_score_outer_block_once |
| `matched_control` | same_outer_matched_issue425_configuration_without_added_family |
| `family_source_gate` | issue426-source-plan-v2 |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `plan_id` | str |
| `status` | str |
| `supersedes` | str |
| `supersession_reason` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `base_configuration` | str |
| `selection_rule` | str |
| `matched_control` | str |
| `family_source_gate` | str |
| `roles` | object (7 keys) |
| `held_role_policy` | object (2 keys) |
| `stages` | array (5 items) |
| `rules` | array (6 items) |
