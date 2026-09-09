<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/forecast-translation-contract.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/forecast-translation-contract.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 005-fundamental-balance |
| `design_id` | rep-014-monthly-real-time-forecastability |
| `issue` | 327 |
| `status` | fixed_before_rep014_translation_outcome_execution |
| `evaluation_contract` | research/programmes/002-henry-hub-fresh/phase1-evaluation-contract.json |
| `evaluation_contract_sha256` | 3c2fb43f1239d59c7ed1aa1d5fb997fec89478219df8139e95b0b062165169f4 |
| `literature_reproduction` | literature-reproduction.json |
| `literature_reproduction_sha256` | f811a5fcb7c477378078baa07bc43c2e524fc3a7949adc01af7897bd5cdcaa93 |
| `source_package_manifest_sha256` | 3d8ad1e8e3226fd22924b298ce08ddb71b2133200e8c6cba785d5bf55fbf172f |
| `selection_basis` | Use one source-faithful parsimonious model fixed from the successfully reproduced external literature before Commodity translation outcomes are scored; do not tune model family, lag order, horizon, threshold, or transformations on Commodity research OOS. |
| `benchmark` | source-study monthly no-change forecast of the real Henry Hub spot price |
| `horizon_policy` | Evaluate the complete predeclared horizon family; no post-outcome horizon selection. |
| `prediction_time` | end of BHLR source-vintage month under a conservative 23:59 UTC monthly availability bound |
| `target` | source-study ex-post real Henry Hub spot price at each declared horizon |
| `pit_rule` | all challenger inputs come from the exact BHLR historical real-time vintage at the forecast origin; final revised values are outcome truth only |
| `protected_confirmation_accessed` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `research_line_id` | str |
| `design_id` | str |
| `issue` | int |
| `status` | str |
| `evaluation_contract` | str |
| `evaluation_contract_sha256` | str |
| `literature_reproduction` | str |
| `literature_reproduction_sha256` | str |
| `source_package_manifest_sha256` | str |
| `selection_basis` | str |
| `challenger` | object (5 keys) |
| `benchmark` | str |
| `horizons_months` | array (9 items) |
| `horizon_policy` | str |
| `chronology` | object (8 keys) |
| `prediction_time` | str |
| `target` | str |
| `pit_rule` | str |
| `evaluation` | object (10 keys) |
| `family_disposition` | object (4 keys) |
| `protected_confirmation_accessed` | bool |
