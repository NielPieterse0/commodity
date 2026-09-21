<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue425-search-plan-v1.json -->

# Issue425 Search Plan V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue425-search-plan-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 425 |
| `programme_issue` | 393 |
| `status` | preregistered_before_issue425_scoring |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `v1_comparator` | research/programmes/003-natural-gas-trading-decision-system/phase6-controlled-expansion-v1.json#frozen_two_year_cadence.yearly_path |
| `v1_comparator_evidence_class` | development_pre_2023_only |
| `sealed_v1_phase7_result_accessed` | false |
| `trial_ledger` | research/programmes/004-v2-maximum-reproducible-one-month-return/issue425-trials-v1.jsonl |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `status` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `protected_evidence` | array (5 items) |
| `objective` | object (3 keys) |
| `validation` | object (6 keys) |
| `v1_comparator` | str |
| `v1_comparator_evidence_class` | str |
| `sealed_v1_phase7_result_accessed` | bool |
| `trial_ledger` | str |
| `search_stages` | array (4 items) |
| `specialist_rules` | object (3 keys) |
| `pruning` | object (3 keys) |
| `stopping_rules` | array (5 items) |
| `revisit_triggers` | array (5 items) |
