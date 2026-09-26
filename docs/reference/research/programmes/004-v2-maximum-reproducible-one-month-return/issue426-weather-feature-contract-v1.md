<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-weather-feature-contract-v1.json -->

# Issue426 Weather Feature Contract V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-weather-feature-contract-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 426 |
| `programme_issue` | 393 |
| `contract_id` | issue426-weather-feature-contract-v1 |
| `status` | preregistered_before_weather_scoring |
| `evidence_class` | development |
| `latest_allowed_trade_date` | 2022-12-31 |
| `source_id` | ncar_gdex_d084001_gfs_0p25_issued_00utc |
| `source_dataset_doi` | 10.5065/D65D8PWK |
| `cycle_utc_hour` | 0 |
| `availability_delay_minutes` | 370 |
| `degree_day_base_c` | 18.3333333333 |
| `anchor_aggregation` | unweighted_anchor_mean |
| `missingness_rule` | do_not_impute_or_silently_fill_unavailable_representation_values_across_information_boundaries |
| `lineage_rule` | verify_each_daily_manifest_source_id_and_anchor_temperature_csv_sha256_before_feature_construction |
| `selection_support_rule` | determine purge-safe minimum-training support per representation first, HOLD representations with no eligible prior inner block, then compare remaining representations only on the chronological intersection of their eligible inner blocks |
| `protected_confirmation_accessed` | false |

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
| `source_id` | str |
| `source_dataset_doi` | str |
| `cycle_utc_hour` | int |
| `availability_delay_minutes` | int |
| `degree_day_base_c` | float |
| `anchor_aggregation` | str |
| `anchors` | array (4 items) |
| `requested_lead_hours` | object (3 keys) |
| `archive_omission_rule` | object (7 keys) |
| `representations` | object (8 keys) |
| `missingness_rule` | str |
| `lineage_rule` | str |
| `selection_support_rule` | str |
| `protected_confirmation_accessed` | bool |
