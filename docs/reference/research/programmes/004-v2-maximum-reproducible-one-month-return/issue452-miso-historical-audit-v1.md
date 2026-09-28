<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-miso-historical-audit-v1.json -->

# Issue452 Miso Historical Audit V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-miso-historical-audit-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 452 |
| `programme_issue` | 393 |
| `audit_id` | issue452-miso-historical-audit-v1 |
| `status` | archive_and_semantics_audit_pass_with_explicit_member_exclusions |
| `evidence_class` | development |
| `protected_confirmation_accessed` | false |
| `power_performance_scored` | false |
| `source` | miso_load_forecast |
| `source_id` | miso_daily_regional_forecast_actual_load_miso_mtlf_v1 |
| `provider` | Midcontinent Independent System Operator |
| `product` | Daily Regional Forecast and Actual Load |
| `archive_index` | MISO Market Reports archived Daily Regional Forecast and Actual Load monthly ZIPs |
| `archive_url_template` | https://docs.misoenergy.org/marketreports/{YYYYMM}_rf_al_xls.zip |
| `member_pattern` | YYYYMMDD_rf_al.xls |
| `next_step` | Implement the bounded MISO capture/normalization path, persist monthly archive/member hashes, rerun this audit from the governed raw archive, and only then score source-identifiable power representations under the superseding source ladder. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `audit_id` | str |
| `status` | str |
| `evidence_class` | str |
| `protected_confirmation_accessed` | bool |
| `power_performance_scored` | bool |
| `source` | str |
| `source_id` | str |
| `provider` | str |
| `product` | str |
| `archive_index` | str |
| `archive_url_template` | str |
| `member_pattern` | str |
| `required_window` | array (2 items) |
| `archive_probe` | object (10 keys) |
| `content_audit` | object (5 keys) |
| `publication_semantics` | object (12 keys) |
| `publication_date_audit` | object (5 keys) |
| `pit_disposition` | object (8 keys) |
| `representation_disposition` | object (3 keys) |
| `next_step` | str |
