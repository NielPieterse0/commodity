<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/002-seasonal-forward-curve/pre-outcome-design.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/002-seasonal-forward-curve/pre-outcome-design.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 001-market-structure |
| `experiment_id` | 002-seasonal-forward-curve |
| `design_id` | rep-002-seasonal-forward-curve |
| `status` | pre_outcome_ready_unfrozen |
| `protected_outcomes_accessed` | false |
| `snapshot_rule` | for each calendar month select the last trade date with at least six simultaneously active exact listed contracts, using identity/expiration only before price access |
| `curve_statistic` | OLS slope beta of ln(final settlement) on normalized exact maturity rank x=(rank-1)/5 for ranks M1..M6; positive beta means prices rise with maturity and negative beta means prices fall with maturity |
| `season_rule` | winter_withdrawal = November-March; injection = April-October |
| `scientific_mepi_standardized` | 0.75 |
| `dry_run_evidence_ref` | research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/002-seasonal-forward-curve/pre-outcome-evidence.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `research_line_id` | str |
| `experiment_id` | str |
| `design_id` | str |
| `status` | str |
| `protected_outcomes_accessed` | bool |
| `snapshot_rule` | str |
| `curve_statistic` | str |
| `season_rule` | str |
| `scientific_mepi_standardized` | float |
| `power` | object (8 keys) |
| `dry_run_evidence_ref` | str |
