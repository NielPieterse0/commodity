<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/003-corrected-kronos-direct-return/experiments/001-kronos-180-corrected-three-checkpoint/confirmation-config.json -->

# Confirmation Config

Source: `research/programmes/001-commodity-natural-gas/lines/003-corrected-kronos-direct-return/experiments/001-kronos-180-corrected-three-checkpoint/confirmation-config.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `experiment_id` | kronos-180-corrected-three-checkpoint-v1 |
| `issue` | 180 |
| `freeze_issue` | 182 |
| `audit_issue` | 183 |
| `status` | frozen_released_with_successor_evaluator_audit |
| `freeze_self_authorizes_execution` | false |
| `historical_evidence_rule` | Consumed #82 evidence remains unchanged and is not part of this experiment identity. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `experiment_id` | str |
| `issue` | int |
| `freeze_issue` | int |
| `audit_issue` | int |
| `status` | str |
| `freeze_self_authorizes_execution` | bool |
| `historical_evidence_rule` | str |
| `implementation_authority` | object (5 keys) |
| `models` | object (3 keys) |
| `common_execution` | object (21 keys) |
| `data_and_target` | object (21 keys) |
| `benchmarks` | object (4 keys) |
| `evaluation` | object (10 keys) |
| `artifacts` | object (5 keys) |
| `resource_observations` | object (3 keys) |
| `decision_rule` | object (6 keys) |
| `release_gate` | object (9 keys) |
| `prohibitions` | array (10 items) |
