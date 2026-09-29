<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-power-weather-result-v1.json -->

# Issue455 Power Weather Result V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-power-weather-result-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `claim_boundary` | development-only incremental MISO power×successor-weather evidence; no protected confirmation, forward, paper, SIM, or LIVE evidence accessed |
| `current_identity_trial_count` | 4 |
| `current_miso_snapshot_identity_sha256` | 0417dac8bc20ba7a75af6329dba37010559bcbd545bcded4455b7abc65a1561e |
| `dataset_id` | 847d4dad534aea6e9dc5a56eedcfb9968dc1ec17ec0e05075292baf39f99278b |
| `evidence_class` | development |
| `execution_code_id` | 3da3f00239000b627640f985c81339c95bb0c8e3fd976d90ecd31215c802f887 |
| `issue` | 455 |
| `issue452_power_result_sha256` | 5d285c79f5b625cbdf8603c362bd42bca3227805105e1fd4272aea36f4ce8b99 |
| `miso_archive_and_feature_hashes_match_issue452` | true |
| `miso_reacquisition_validation_sha256` | b270033fbf1a93fbfe59e5f756a8fcde15eb4d2c076b1464ff1b1d8743bb064d |
| `programme_issue` | 393 |
| `prospective_paper_accessed` | false |
| `protected_confirmation_accessed` | false |
| `saxo_live_accessed` | false |
| `saxo_sim_accessed` | false |
| `schema_version` | 1 |
| `status` | power_successor_weather_interaction_complete |
| `successor_plan_sha256` | b8d76ff738f36a0b010d1c40ac49db52eb66b332b03b5cd37c7ba6f5fb891754 |
| `successor_weather_result_sha256` | 5c750c62c6a5c81ddb69a99eec75a24bc32c7e3cbdf57ac37e10600a54da98bc |
| `trial_count` | 8 |
| `trial_ledger_path` | research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-power-weather-trials-v1.jsonl |
| `trial_ledger_sha256` | b07df110e85545aba05cd875ada197ef4067f2bcc5638ed508b4576b50491701 |
| `true_forward_accessed` | false |

## Structure

| Field | Shape |
| --- | --- |
| `claim_boundary` | str |
| `current_identity_trial_count` | int |
| `current_miso_snapshot_identity_sha256` | str |
| `dataset_id` | str |
| `evidence_class` | str |
| `execution_code_id` | str |
| `interaction` | object (9 keys) |
| `issue` | int |
| `issue452_power_result_sha256` | str |
| `miso_archive_and_feature_hashes_match_issue452` | bool |
| `miso_reacquisition_validation_sha256` | str |
| `programme_issue` | int |
| `prospective_paper_accessed` | bool |
| `protected_confirmation_accessed` | bool |
| `saxo_live_accessed` | bool |
| `saxo_sim_accessed` | bool |
| `schema_version` | int |
| `status` | str |
| `successor_plan_sha256` | str |
| `successor_weather_result_sha256` | str |
| `trial_count` | int |
| `trial_ledger_path` | str |
| `trial_ledger_sha256` | str |
| `true_forward_accessed` | bool |
