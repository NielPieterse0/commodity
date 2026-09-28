<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-nyiso-historical-audit-v1.json -->

# Issue452 Nyiso Historical Audit V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-nyiso-historical-audit-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 452 |
| `audit_id` | issue452-nyiso-historical-audit-v1 |
| `evidence_class` | development |
| `source` | nyiso_load_forecast |
| `source_id` | nyiso_p7_iso_load_forecast |
| `audit_disposition` | HOLD_RETROACTIVE_OVERWRITE_AMBIGUITY |
| `family_disposition` | CONTINUE_SOURCE_LADDER |
| `search_budget_consumed` | false |
| `protected_confirmation_accessed` | false |
| `successful_months_before_failure` | 51 |
| `first_failed_archive` | 2015-04 |
| `first_failed_member` | 20150424isolf.csv |
| `conservative_availability_basis` | noon_America_New_York_on_operating_day |
| `partial_archive_note` | The already captured 2011-01 through 2015-03 snapshots remain useful source evidence but are not sufficient to admit the full development family. |
| `next_source` | iso_ne_load_forecast |
| `next_action` | bind_exact_iso_ne_issued_forecast_product_publication_semantics_and_historical_archive_before_any_power_scoring |
| `no_post_hoc_relaxation` | true |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `audit_id` | str |
| `evidence_class` | str |
| `source` | str |
| `source_id` | str |
| `required_window` | array (2 items) |
| `audit_disposition` | str |
| `family_disposition` | str |
| `search_budget_consumed` | bool |
| `protected_confirmation_accessed` | bool |
| `successful_months_before_failure` | int |
| `first_failed_archive` | str |
| `first_failed_member` | str |
| `conservative_availability_basis` | str |
| `failure` | object (4 keys) |
| `parallel_format_check` | object (4 keys) |
| `integrity_controls_preserved` | array (6 items) |
| `partial_archive_note` | str |
| `next_source` | str |
| `next_action` | str |
| `no_post_hoc_relaxation` | bool |
