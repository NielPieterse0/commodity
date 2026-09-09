<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/forecast-preparation.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/forecast-preparation.json`

## Overview

| Field | Value |
| --- | --- |
| `boundary_label` | 24-month target availability |
| `design_id` | rep-014-monthly-real-time-forecastability |
| `evaluation_contract_sha256` | 3c2fb43f1239d59c7ed1aa1d5fb997fec89478219df8139e95b0b062165169f4 |
| `forecast_translation_contract_sha256` | b9a08cbfa5f2fc8b7631ee0f02db6a96071be7b89f90c37c82cd90d6ae2cf34f |
| `issue` | 327 |
| `model_fitting_performed` | false |
| `prediction_scoring_performed` | false |
| `preparation_verification_scope` | full_prepared_frame |
| `preparation_verification_status` | passed |
| `prepared_rows` | 86 |
| `programme_id` | 002-henry-hub-fresh |
| `purged_boundary_rows` | 24 |
| `research_end` | 2018-08-31T23:59:59+00:00 |
| `research_line_id` | 005-fundamental-balance |
| `research_rows_after_overlap_purge` | 44 |
| `research_start` | 2015-01-31T23:59:59+00:00 |
| `reserved_end` | 2022-02-28T23:59:59+00:00 |
| `reserved_fraction` | 0.20930232558139536 |
| `reserved_outcomes_human_inspected` | false |
| `reserved_outcomes_scored` | false |
| `reserved_rows` | 18 |
| `reserved_start` | 2020-09-30T23:59:59+00:00 |
| `schema_version` | 1 |
| `source_package_manifest_sha256` | 3d8ad1e8e3226fd22924b298ce08ddb71b2133200e8c6cba785d5bf55fbf172f |
| `status` | prepared_reserved_research_capacity_hold |

## Structure

| Field | Shape |
| --- | --- |
| `boundary_label` | str |
| `design_id` | str |
| `evaluation_contract_sha256` | str |
| `forecast_translation_contract_sha256` | str |
| `horizons_months` | array (9 items) |
| `issue` | int |
| `model_fitting_performed` | bool |
| `prediction_scoring_performed` | bool |
| `preparation_verification_scope` | str |
| `preparation_verification_status` | str |
| `prepared_rows` | int |
| `programme_id` | str |
| `purged_boundary_rows` | int |
| `research_end` | str |
| `research_line_id` | str |
| `research_oos_capacity` | object (5 keys) |
| `research_rows_after_overlap_purge` | int |
| `research_start` | str |
| `reserved_end` | str |
| `reserved_fraction` | float |
| `reserved_outcomes_human_inspected` | bool |
| `reserved_outcomes_scored` | bool |
| `reserved_rows` | int |
| `reserved_start` | str |
| `schema_version` | int |
| `sealed_window` | object (9 keys) |
| `source_package_manifest_sha256` | str |
| `status` | str |
