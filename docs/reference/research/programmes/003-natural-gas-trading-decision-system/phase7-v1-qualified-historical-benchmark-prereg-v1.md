<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/003-natural-gas-trading-decision-system/phase7-v1-qualified-historical-benchmark-prereg-v1.json -->

# 003-natural-gas-trading-decision-system

Source: `research/programmes/003-natural-gas-trading-decision-system/phase7-v1-qualified-historical-benchmark-prereg-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 003-natural-gas-trading-decision-system |
| `phase` | 7 |
| `issue` | 361 |
| `benchmark_id` | v1-qualified-historical-2023plus-v1 |
| `status` | authorized_pending_execution |
| `operator_authorized_date` | 2026-09-13 |
| `purpose` | Record frozen v1 performance on the reserved post-2022 historical block before v2 development starts. |
| `evidence_class` | foundation_model_qualified_historical_evidence |
| `clean_confirmation_eligible` | false |
| `qualification_reason` | TimesFM and Kronos checkpoint pretraining exposure prevents a pristine historical-confirmation claim, but the block remained unused for v1 selection and is valid as a one-shot frozen historical benchmark. |
| `interpretation_rule` | The result becomes v1's immutable historical benchmark for v2 comparisons. It may inform v2 design only after it is durably recorded; it must never trigger tuning or rewriting of v1. |
| `prospective_evidence_rule` | This historical benchmark does not replace or upgrade the separate true-forward Phase-7 prospective evidence contract. |
| `live_capital_authorized` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `phase` | int |
| `issue` | int |
| `benchmark_id` | str |
| `status` | str |
| `operator_authorized_date` | str |
| `purpose` | str |
| `evidence_class` | str |
| `clean_confirmation_eligible` | bool |
| `qualification_reason` | str |
| `window` | object (3 keys) |
| `frozen_candidate` | object (6 keys) |
| `specialist_contract` | object (3 keys) |
| `replay_contract` | object (9 keys) |
| `reported_metrics` | array (11 items) |
| `informational_comparator` | object (3 keys) |
| `interpretation_rule` | str |
| `prospective_evidence_rule` | str |
| `live_capital_authorized` | bool |
