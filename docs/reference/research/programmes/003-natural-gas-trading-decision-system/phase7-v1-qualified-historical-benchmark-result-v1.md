<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/003-natural-gas-trading-decision-system/phase7-v1-qualified-historical-benchmark-result-v1.json -->

# 003-natural-gas-trading-decision-system

Source: `research/programmes/003-natural-gas-trading-decision-system/phase7-v1-qualified-historical-benchmark-result-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `benchmark_id` | v1-qualified-historical-2023plus-v1 |
| `clean_confirmation_eligible` | false |
| `completed_at_utc` | 2026-09-13T20:13:47Z |
| `evidence_class` | foundation_model_qualified_historical_evidence |
| `interpretation_boundary` | The result becomes v1's immutable historical benchmark for v2 comparisons. It may inform v2 design only after it is durably recorded; it must never trigger tuning or rewriting of v1. |
| `issue` | 361 |
| `phase` | 7 |
| `programme_id` | 003-natural-gas-trading-decision-system |
| `prospective_evidence_rule` | This historical benchmark does not replace or upgrade the separate true-forward Phase-7 prospective evidence contract. |
| `raw_runtime_result_sha256` | 631c32d1ccfa0d73f469ade1b72538bf5ed154b172bb7e81259544527f241026 |
| `runtime_path_policy` | Machine-specific runtime paths from the execution result are intentionally not persisted; all retained evidence is repository-relative and hash-bound. |
| `schema_version` | 1 |
| `status` | complete |

## Structure

| Field | Shape |
| --- | --- |
| `benchmark_id` | str |
| `clean_confirmation_eligible` | bool |
| `comparison` | object (3 keys) |
| `completed_at_utc` | str |
| `coverage` | object (4 keys) |
| `evidence_class` | str |
| `evidence_files` | object (5 keys) |
| `execution_boundary` | object (4 keys) |
| `interpretation_boundary` | str |
| `issue` | int |
| `market_only_no_modifier_comparator` | object (18 keys) |
| `phase` | int |
| `preregistration` | object (2 keys) |
| `programme_id` | str |
| `prospective_evidence_rule` | str |
| `raw_runtime_result_sha256` | str |
| `runtime_path_policy` | str |
| `schema_version` | int |
| `status` | str |
| `v1` | object (18 keys) |
