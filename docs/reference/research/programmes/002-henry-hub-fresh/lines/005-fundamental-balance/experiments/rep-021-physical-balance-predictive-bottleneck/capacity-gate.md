<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-021-physical-balance-predictive-bottleneck/capacity-gate.json -->

# Capacity Gate

Source: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-021-physical-balance-predictive-bottleneck/capacity-gate.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `design_id` | rep-021-physical-balance-predictive-bottleneck |
| `status` | passed_before_outcome_scoring_with_detectability_caveat |
| `computed_on` | 2026-09-09 |
| `outcomes_accessed` | false |
| `candidate_predictor_rows` | 284 |
| `candidate_predictor_rows_usable` | 284 |
| `development_rows` | 72 |
| `research_oos_rows` | 212 |
| `model_capacity` | fixed ridge alpha 10; no search; simultaneous three-feature physical addition |
| `detectability_method` | outcome-blind Gaussian paired-loss planning approximation using OOS_rows/block_months as effective independent blocks; 80% power, two-sided 5% size |
| `detectability_interpretation` | The 1% promotion threshold is a decision threshold, not guaranteed power. Under the primary three-month dependence assumption, an effect near 1% is only well powered when paired errors are extremely highly correlated; weaker marginal effects may remain inconclusive. |
| `sensitivity_policy` | Primary scientific disposition uses block=3 months only. Block=1 and block=6 are reported as robustness sensitivities and cannot rescue a failed primary result. |
| `protected_confirmation_accessed` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `design_id` | str |
| `status` | str |
| `computed_on` | str |
| `outcomes_accessed` | bool |
| `candidate_predictor_rows` | int |
| `candidate_predictor_rows_usable` | int |
| `development_rows` | int |
| `research_oos_rows` | int |
| `model_feature_counts` | object (3 keys) |
| `model_capacity` | str |
| `moving_block_bootstrap` | object (5 keys) |
| `detectability_method` | str |
| `detectability_primary_block` | object (4 keys) |
| `detectability_interpretation` | str |
| `proceed_rule` | object (2 keys) |
| `sensitivity_policy` | str |
| `protected_confirmation_accessed` | bool |
