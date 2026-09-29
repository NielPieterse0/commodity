<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-successor-weather-baseline-v1.json -->

# Issue455 Successor Weather Baseline V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-successor-weather-baseline-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `claim_boundary` | development-only successor weather baseline; no protected confirmation, forward, paper, SIM, or LIVE evidence accessed |
| `complete` | true |
| `dataset_frozen` | true |
| `development_disposition` | HOLD_STANDALONE_NO_MATCHED_MARGINAL_VALUE_REGISTERED_INTERACTIONS_STILL_REQUIRED |
| `evidence_class` | development |
| `execution_code_id` | 3da3f00239000b627640f985c81339c95bb0c8e3fd976d90ecd31215c802f887 |
| `issue` | 455 |
| `mean_monthly_net_return_delta` | -0.001034693877551018 |
| `pit_safe` | true |
| `programme_issue` | 393 |
| `prospective_paper_accessed` | false |
| `protected_confirmation_accessed` | false |
| `saxo_live_accessed` | false |
| `saxo_sim_accessed` | false |
| `schema_version` | 1 |
| `scoring_dataset_id` | 987bfe7dd56b30dca8f7fbfdad781d7b9c2c0e4926a39830c8c13bac2d01de3d |
| `status` | successor_weather_baseline_complete |
| `successor_plan_sha256` | b8d76ff738f36a0b010d1c40ac49db52eb66b332b03b5cd37c7ba6f5fb891754 |
| `successor_weather_dataset_id` | 5353b62ea811c5bbe9b12acd6a66c3a2f26ce568fce153cd887aca52d5aca8b9 |
| `trial_count` | 230 |
| `trial_ledger_path` | research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-successor-weather-trials-v1.jsonl |
| `trial_ledger_sha256` | 97095d2d462afd8a92619521ab64c79c20ee9fb74ef05eaf0301146a1a1c2c4d |
| `true_forward_accessed` | false |
| `weather_rows` | 2908 |

## Structure

| Field | Shape |
| --- | --- |
| `claim_boundary` | str |
| `complete` | bool |
| `dataset_frozen` | bool |
| `development_disposition` | str |
| `evidence_class` | str |
| `execution_code_id` | str |
| `issue` | int |
| `matched_control_score` | object (13 keys) |
| `mean_monthly_net_return_delta` | float |
| `nested_outer` | array (2 items) |
| `nested_selection_score` | object (13 keys) |
| `pit_safe` | bool |
| `programme_issue` | int |
| `prospective_paper_accessed` | bool |
| `protected_confirmation_accessed` | bool |
| `saxo_live_accessed` | bool |
| `saxo_sim_accessed` | bool |
| `schema_version` | int |
| `scoring_dataset_id` | str |
| `skipped_outer` | array (1 items) |
| `status` | str |
| `successor_plan_sha256` | str |
| `successor_weather_dataset_id` | str |
| `trial_count` | int |
| `trial_ledger_path` | str |
| `trial_ledger_sha256` | str |
| `true_forward_accessed` | bool |
| `weather_rows` | int |
