<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v2.json -->

# Issue426 Optimization Plan V2

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v2.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 426 |
| `programme_issue` | 393 |
| `plan_id` | issue426-optimization-plan-v2 |
| `status` | registered_before_historical_family_scoring |
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
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `base_configuration` | str |
| `selection_rule` | str |
| `matched_control` | str |
| `family_source_gate` | str |
| `roles` | object (7 keys) |
| `stages` | array (5 items) |
| `rules` | array (4 items) |
