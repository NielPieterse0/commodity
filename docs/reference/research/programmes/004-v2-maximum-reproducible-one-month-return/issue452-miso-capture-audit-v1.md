<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-miso-capture-audit-v1.json -->

# Issue452 Miso Capture Audit V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-miso-capture-audit-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `actual_load_current_day_forbidden` | true |
| `all_member_hashes_valid` | true |
| `archive_member_count` | 4383 |
| `archive_month_count` | 144 |
| `audit_id` | issue452-miso-capture-audit-v1 |
| `availability_basis` | miso_internal_published_date_plus_one_day_0000_fixed_est |
| `evidence_class` | development |
| `excluded_member_count` | 9 |
| `forecast_hours_per_accepted_day` | 24 |
| `issue` | 452 |
| `manifest_index_sha256` | dd28e7a8ab08c39a735f68c366e46eaae7fb2cd7269fe1ccfdb5428f854d78ea |
| `programme_issue` | 393 |
| `protected_confirmation_accessed` | false |
| `required_end` | 2022-12-31 |
| `required_start` | 2011-01-01 |
| `research_pit_ready` | true |
| `revision_status` | single_daily_issue_same_target_revision_not_identifiable |
| `schema_version` | 1 |
| `source` | miso_load_forecast |
| `source_id` | miso_daily_regional_forecast_actual_load_miso_mtlf_v1 |
| `status` | PASS |
| `usable_day_count` | 4374 |

## Structure

| Field | Shape |
| --- | --- |
| `actual_load_current_day_forbidden` | bool |
| `all_member_hashes_valid` | bool |
| `archive_member_count` | int |
| `archive_month_count` | int |
| `audit_id` | str |
| `availability_basis` | str |
| `evidence_class` | str |
| `excluded_member_count` | int |
| `excluded_members` | array (9 items) |
| `forecast_hours_per_accepted_day` | int |
| `issue` | int |
| `manifest_index_sha256` | str |
| `monthly_manifests` | array (144 items) |
| `programme_issue` | int |
| `protected_confirmation_accessed` | bool |
| `required_end` | str |
| `required_start` | str |
| `research_pit_ready` | bool |
| `revision_status` | str |
| `schema_version` | int |
| `source` | str |
| `source_id` | str |
| `status` | str |
| `usable_day_count` | int |
