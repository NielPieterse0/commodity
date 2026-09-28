<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-pjm-publication-contract-v1.json -->

# Issue452 Pjm Publication Contract V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-pjm-publication-contract-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 452 |
| `programme_issue` | 393 |
| `contract_id` | issue452-pjm-publication-contract-v1 |
| `status` | preregistered_before_pjm_power_scoring |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `protected_confirmation_accessed` | false |
| `source_id` | pjm_load_frcstd_hist_rto_vintage_pit_v1 |
| `archive_feed` | load_frcstd_hist |
| `publication_feed` | load_frcstd_7_day |
| `forecast_area` | RTO |
| `scoring_rule` | PJM power may enter #426-matched development scoring only after archive integrity, revision preservation and publication-time reconstruction all pass. |
| `fallback` | If historical archive acquisition or vintage integrity cannot be established, retain HOLD or replace with a separately preregistered PIT-safe power source; do not weaken this contract. |

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
| `source_id` | str |
| `archive_feed` | str |
| `publication_feed` | str |
| `forecast_area` | str |
| `archive_fields` | array (6 items) |
| `time_semantics` | object (3 keys) |
| `availability_rule` | object (7 keys) |
| `revision_gate` | object (5 keys) |
| `pit_gate` | object (4 keys) |
| `authority` | array (4 items) |
| `corroboration_only` | array (1 items) |
| `scoring_rule` | str |
| `fallback` | str |
