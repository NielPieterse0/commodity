<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/002-volatility-195-gk-har-v1/coverage.json -->

# Coverage

Source: `research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/002-volatility-195-gk-har-v1/coverage.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `experiment_id` | volatility-195-gk-har-v1 |
| `issue` | 195 |
| `authority` | diagnostic_only_consumed_phase_d_history |
| `candidate_rows` | 456 |
| `initial_train_rows` | 252 |
| `scored_rows` | 204 |
| `candidate_start` | 2024-09-12T23:59:00+00:00 |
| `candidate_end` | 2026-08-11T23:59:00+00:00 |
| `oos_start` | 2025-10-03T23:59:00+00:00 |
| `oos_end` | 2026-08-11T23:59:00+00:00 |
| `candidate_prediction_times_sha256` | fe2814ad84ba4ed790fa9e9b0d386056ec0902f09817167ed0189ee80c98f6ff |
| `candidate_prediction_times_path` | candidate-prediction-times.txt |
| `scored_prediction_times_sha256` | 0893c78680a0aac8d6c17a4138bcaa863f415fa1e4aa9dc979dbd2ec0d44841a |
| `scored_prediction_times_path` | predictions.csv#prediction_time |
| `prediction_time_hash_preimage` | newline_joined_exact_source_timestamp_strings_with_terminal_newline |
| `selected_contract_rows` | 456 |
| `selected_contract_count` | 24 |
| `minimum_same_contract_history_rows` | 21 |
| `required_same_contract_history_rows` | 20 |
| `missing_next_session_same_contract_targets` | 0 |
| `invalid_target_ohlc_rows` | 0 |
| `row_drops` | 0 |
| `target_imputations` | 0 |
| `cross_contract_substitutions` | 0 |
| `dataset_sha256` | 0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f |
| `canonical_market_sha256` | 83faf07a8de1fe3fea4cd6548dd25d9c02828e1ef4faa13a234ac8f2ad03d655 |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `experiment_id` | str |
| `issue` | int |
| `authority` | str |
| `candidate_rows` | int |
| `initial_train_rows` | int |
| `scored_rows` | int |
| `candidate_start` | str |
| `candidate_end` | str |
| `oos_start` | str |
| `oos_end` | str |
| `candidate_prediction_times_sha256` | str |
| `candidate_prediction_times_path` | str |
| `scored_prediction_times_sha256` | str |
| `scored_prediction_times_path` | str |
| `prediction_time_hash_preimage` | str |
| `selected_contract_rows` | int |
| `selected_contract_count` | int |
| `minimum_same_contract_history_rows` | int |
| `required_same_contract_history_rows` | int |
| `missing_next_session_same_contract_targets` | int |
| `invalid_target_ohlc_rows` | int |
| `row_drops` | int |
| `target_imputations` | int |
| `cross_contract_substitutions` | int |
| `dataset_sha256` | str |
| `canonical_market_sha256` | str |
