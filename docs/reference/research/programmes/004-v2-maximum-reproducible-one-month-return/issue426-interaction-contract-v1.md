<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-interaction-contract-v1.json -->

# Issue426 Interaction Contract V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-interaction-contract-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 426 |
| `programme_issue` | 393 |
| `contract_id` | issue426-interaction-contract-v1 |
| `status` | preregistered_before_combined_interaction_scoring |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `protected_confirmation_accessed` | false |
| `required_interaction` | storage×weather×season×volatility |
| `activation_rule` | score_only_when_storage_and_weather_both_pass_the_registered_historical_source_gate |
| `selection_rule` | select_on_the_chronological_intersection_of_strictly_prior_inner_blocks_supporting_both_selected_family_representations_then_score_the_outer_block_once |
| `family_representation_rule` | use_each_outer_blocks_storage_and_weather_representations_selected_without_outer_evidence |
| `candidate_increment` | pure_four_way_interaction_features_added_to_the_exact_outer_matched_issue425_market_control |
| `formula` | storage_value * weather_value * season_component * feature_vol_20 |
| `lower_order_family_main_effects_in_combined_candidate` | false |
| `transform_basis_retain` | 1 |
| `matched_control` | same_origins_same_transform_basis_exact_outer_issue425_market_features_without_combined_interaction_columns |
| `power_weather_disposition` | HOLD_WHILE_POWER_SOURCE_GATE_IS_HOLD |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `contract_id` | str |
| `status` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `protected_confirmation_accessed` | bool |
| `required_interaction` | str |
| `activation_rule` | str |
| `selection_rule` | str |
| `family_representation_rule` | str |
| `candidate_increment` | str |
| `formula` | str |
| `season_components` | array (2 items) |
| `lower_order_family_main_effects_in_combined_candidate` | bool |
| `transform_basis_candidates` | array (2 items) |
| `transform_basis_retain` | int |
| `matched_control` | str |
| `power_weather_disposition` | str |
| `rules` | array (4 items) |
