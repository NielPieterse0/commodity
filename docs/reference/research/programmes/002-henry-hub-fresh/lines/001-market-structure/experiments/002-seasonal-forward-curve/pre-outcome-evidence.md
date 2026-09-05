<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/002-seasonal-forward-curve/pre-outcome-evidence.json -->

# Pre Outcome Evidence

Source: `research/programmes/002-henry-hub-fresh/lines/001-market-structure/experiments/002-seasonal-forward-curve/pre-outcome-evidence.json`

## Overview

| Field | Value |
| --- | --- |
| `archive_complete_through` | 2026-08-12 |
| `archive_id` | databento-ng-full-history-v1 |
| `change_local_dry_run_sha256` | c581dd32e8c62bbc815749a52133967cfb7b1b9d4ca0bde90592b0740fa5f7ef |
| `conclusion` | Outcome-blind identity-only dry run confirms all 195 calendar months have an eligible exact-contract M1-M6 snapshot; settlement prices were not accessed. |
| `definition_manifest_sha256` | 28384d503e8edb3bb06f28c5e0c7c527af1a6af7967665028c2590ab8d8fb0f4 |
| `design_id` | rep-002-seasonal-forward-curve |
| `evidence_class` | outcome_blind_archive_dry_run |
| `experiment_id` | 002-seasonal-forward-curve |
| `identity_semantics` | instrument_id and definition payload are resolved point-in-time; provider-undefined timestamps are excluded; no global symbol-to-expiration mapping |
| `protected_outcomes_accessed` | false |
| `runner_sha256` | 01e99c9ee59a7f73bd3435048ba81a946be506cf4943e8e0f81793e02329874d |
| `schema_version` | 1 |
| `statistics_manifest_sha256` | 506142d2e8668be0d2cbd9ec2f99565c87de6066dc605fb868df9b927f291a30 |

## Structure

| Field | Shape |
| --- | --- |
| `archive_complete_through` | str |
| `archive_id` | str |
| `change_local_dry_run_sha256` | str |
| `conclusion` | str |
| `definition_manifest_sha256` | str |
| `design_id` | str |
| `evidence_class` | str |
| `experiment_id` | str |
| `identity_semantics` | str |
| `power` | object (9 keys) |
| `protected_outcomes_accessed` | bool |
| `runner_sha256` | str |
| `sample` | object (5 keys) |
| `schema_version` | int |
| `statistics_access_contract` | object (3 keys) |
| `statistics_manifest_sha256` | str |
