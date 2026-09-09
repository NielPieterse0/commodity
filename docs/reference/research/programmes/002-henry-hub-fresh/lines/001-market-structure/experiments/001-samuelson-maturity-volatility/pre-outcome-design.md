<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/001-samuelson-maturity-volatility/pre-outcome-design.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/001-samuelson-maturity-volatility/pre-outcome-design.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 001-market-structure |
| `experiment_id` | 001-samuelson-maturity-volatility |
| `design_id` | rep-001-samuelson-maturity-volatility |
| `status` | pre_outcome_ready_unfrozen |
| `protected_outcomes_accessed` | false |
| `primary_proxy` | absolute same-contract daily log return |
| `liquidity_rule` | finite cleared volume > 0 |
| `season_rule` | winter_withdrawal Nov-Mar; non_winter Apr-Oct |
| `scientific_mepi_standardized` | 0.25 |
| `dry_run_evidence_ref` | research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/001-samuelson-maturity-volatility/pre-outcome-evidence.json |

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
| `primary_proxy` | str |
| `dte_buckets` | array (6 items) |
| `liquidity_rule` | str |
| `season_rule` | str |
| `scientific_mepi_standardized` | float |
| `power` | object (8 keys) |
| `dry_run_evidence_ref` | str |
