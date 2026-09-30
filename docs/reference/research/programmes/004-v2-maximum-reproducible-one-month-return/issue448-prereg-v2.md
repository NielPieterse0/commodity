<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-prereg-v2.json -->

# 004-v2-maximum-reproducible-one-month-return

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-prereg-v2.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 448 |
| `programme_issue` | 393 |
| `programme_id` | 004-v2-maximum-reproducible-one-month-return |
| `plan_id` | issue448-prereg-v2 |
| `status` | preregistered_before_issue448_empirical_scoring |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `protected_confirmation_accessed` | false |
| `purpose` | Close bounded classical and quantitative coverage gaps before model-family optimization without duplicating information already present in the V2 market baseline. |
| `supersedes` | issue448-prereg-v1 |
| `supersession_reason` | No-scoring 2010-2022 source coverage audit proved PIT-safe open interest starts too late for the standard early outer blocks under the established 504-row incremental-family minimum; register an availability-aligned OI lane before any empirical family scoring. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `programme_id` | str |
| `plan_id` | str |
| `status` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `protected_confirmation_accessed` | bool |
| `purpose` | str |
| `authority` | object (4 keys) |
| `selection_contract` | object (8 keys) |
| `technical_analysis` | object (7 keys) |
| `market_structure` | object (7 keys) |
| `storage_surprise_gate` | object (4 keys) |
| `scheduled_event_timing` | object (4 keys) |
| `volatility_tail_handoff` | object (4 keys) |
| `options_implied_gate` | object (7 keys) |
| `dispositions` | object (4 keys) |
| `rules` | array (8 items) |
| `supersedes` | str |
| `supersession_reason` | str |
