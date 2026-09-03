<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/003-volatility-successor-power-gated-197-209/event-release-audit.json -->

# Event Release Audit

Source: `research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/003-volatility-successor-power-gated-197-209/event-release-audit.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `release_id` | volatility-event-successor-205-calibration-release-v1 |
| `issue` | 207 |
| `decision` | pass_nuisance_calibration_only |
| `audited_main` | 4dab55b89afb68ff8c92c8a09383f39133c8b5a6 |
| `audited_at` | 2026-08-26 |
| `freeze_id` | volatility-event-successor-205-v1 |
| `release_condition` | Run only the frozen 80-event nuisance calibration. All 2/4/8-event relative MDEs at exact confirmation n=342 must be <= 0.05 before any confirmation performance may be opened. |
| `evidence_note` | Audit used only row identity, contract identity, source coverage, calendar ordering, same-contract history, OHLC validity and PIT availability. No candidate-confirmation volatility, forecast, QLIKE, improvement, significance, period/regime or secondary performance was calculated or inspected. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `release_id` | str |
| `issue` | int |
| `decision` | str |
| `audited_main` | str |
| `audited_at` | str |
| `freeze_id` | str |
| `identities` | object (5 keys) |
| `source_authority` | object (7 keys) |
| `schedule_audit` | object (10 keys) |
| `roles` | object (4 keys) |
| `protected_evidence` | object (3 keys) |
| `authority` | object (7 keys) |
| `forbidden_calibration_outputs` | array (7 items) |
| `release_condition` | str |
| `evidence_note` | str |
