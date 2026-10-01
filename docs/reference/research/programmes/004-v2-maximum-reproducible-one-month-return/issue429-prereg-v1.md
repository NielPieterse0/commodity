<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue429-prereg-v1.json -->

# Issue429 Prereg V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue429-prereg-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 429 |
| `revision` | 1 |
| `status` | frozen_before_issue429_scoring |
| `evidence_class` | development |
| `claim_boundary` | development_discovery_only_no_confirmed_edge_claim |
| `fixed_parent_model_rule` | retain each outer's issue427 selected model config and its forecast outputs for every issue429 contribution and lifecycle comparison |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `revision` | int |
| `status` | str |
| `evidence_class` | str |
| `claim_boundary` | str |
| `evidence_boundary` | object (5 keys) |
| `parent` | object (8 keys) |
| `fixed_parent_model_rule` | str |
| `contribution_ablation` | object (3 keys) |
| `lifecycle_search` | object (5 keys) |
| `event_time_lane` | object (3 keys) |
| `evaluation` | object (7 keys) |
| `effective_sample_controls` | object (4 keys) |
| `promotion_gate` | object (6 keys) |
| `fixed_safety` | object (4 keys) |
