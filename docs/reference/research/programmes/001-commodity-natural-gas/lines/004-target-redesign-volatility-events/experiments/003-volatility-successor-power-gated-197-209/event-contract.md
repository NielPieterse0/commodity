<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/003-volatility-successor-power-gated-197-209/event-contract.json -->

# Event Contract

Source: `research/programmes/001-commodity-natural-gas/lines/004-target-redesign-volatility-events/experiments/003-volatility-successor-power-gated-197-209/event-contract.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `contract_id` | volatility-event-successor-205-v1 |
| `issue` | 205 |
| `status` | frozen_design_execution_unauthorized |
| `assessment_date` | 2026-08-26 |
| `purpose` | Replace the underpowered daily #197 confirmation with a non-overlapping 5-session realized-volatility design whose power must be revalidated before confirmation. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `contract_id` | str |
| `issue` | int |
| `status` | str |
| `assessment_date` | str |
| `purpose` | str |
| `lineage` | object (4 keys) |
| `protected_evidence` | object (4 keys) |
| `prediction` | object (6 keys) |
| `target` | object (7 keys) |
| `features` | object (5 keys) |
| `models` | object (6 keys) |
| `loss` | object (3 keys) |
| `sample` | object (11 keys) |
| `power_calibration` | object (6 keys) |
| `inference` | object (8 keys) |
| `activation_gates` | object (8 keys) |
| `authority` | object (6 keys) |
| `stop_rules` | array (4 items) |
