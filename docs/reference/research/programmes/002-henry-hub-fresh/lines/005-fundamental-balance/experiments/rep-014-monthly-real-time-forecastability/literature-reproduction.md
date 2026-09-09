<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/literature-reproduction.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-014-monthly-real-time-forecastability/literature-reproduction.json`

## Overview

| Field | Value |
| --- | --- |
| `design_id` | rep-014-monthly-real-time-forecastability |
| `durable_manifest_sha256` | 3d8ad1e8e3226fd22924b298ce08ddb71b2133200e8c6cba785d5bf55fbf172f |
| `exact_published_cell_matches` | 58 |
| `forecast_translation_role` | not_scored_by_literature_reproduction |
| `interpretation` | The BHLR real-time forecastability result is independently reproduced in Python: both parsimonious six-variable VAR(1) specifications beat no-change at every reported 1-24 month horizon, and the model-free Table 1 results reproduce except for one ancillary EIA expert h=6 paper/package discrepancy. |
| `issue` | 327 |
| `literature_disposition` | REPRODUCED_WITH_ONE_ANCILLARY_PACKAGE_TABLE_DISCREPANCY |
| `literature_gate_closed` | true |
| `method` | Independent Python translation from source-study raw real-time inputs; author saved losses used only as a secondary audit. |
| `package_loss_audit_passed` | true |
| `programme_id` | 002-henry-hub-fresh |
| `protected_confirmation_accessed` | false |
| `published_cells_checked` | 59 |
| `replication_class_achieved` | exact_replication_python_translation_subset |
| `replication_class_target` | exact_replication_then_independent_near_replication |
| `replication_data_doi` | 10.15456/jae.2025266.1900967125 |
| `research_line_id` | 005-fundamental-balance |
| `schema_version` | 1 |
| `source_study_doi` | 10.1002/jae.70018 |
| `zoom_level` | L5 |

## Structure

| Field | Shape |
| --- | --- |
| `design_id` | str |
| `durable_manifest_sha256` | str |
| `exact_published_cell_matches` | int |
| `forecast_translation_role` | str |
| `interpretation` | str |
| `issue` | int |
| `literature_disposition` | str |
| `literature_gate_closed` | bool |
| `method` | str |
| `package_loss_audit_passed` | bool |
| `programme_id` | str |
| `protected_confirmation_accessed` | bool |
| `published_cells_checked` | int |
| `replication_class_achieved` | str |
| `replication_class_target` | str |
| `replication_data_doi` | str |
| `research_line_id` | str |
| `schema_version` | int |
| `source_study_doi` | str |
| `table1` | object (7 keys) |
| `table3_var1` | object (8 keys) |
| `zoom_level` | str |
