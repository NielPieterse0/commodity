<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/475-full-history-adaptive-edge/design-freeze.json -->

# Design Freeze

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/475-full-history-adaptive-edge/design-freeze.json`

## Overview

| Field | Value |
| --- | --- |
| `issue` | 475 |
| `preflight_sha256` | 6a0d4af91597646fd35f8b7bc9d2257124b58b2a4b56dc2bc90af5966b8c57af |
| `protected_confirmation_accessed` | false |
| `protected_start` | 2023-01-01T00:00:00+00:00 |
| `schema_version` | 1 |
| `selection_rule` | smallest architecture passing all frozen robustness gates |
| `status` | FROZEN_BEFORE_AUTHORITATIVE_TRAVERSAL |

## Structure

| Field | Shape |
| --- | --- |
| `authority_identity` | object (4 keys) |
| `benchmark_contract` | array (7 items) |
| `candidate_specs` | array (13 items) |
| `identity` | object (7 keys) |
| `issue` | int |
| `no_rescue_rules` | array (4 items) |
| `preflight_sha256` | str |
| `prequential_config` | object (14 keys) |
| `protected_confirmation_accessed` | bool |
| `protected_start` | str |
| `robustness_config` | object (7 keys) |
| `role_dispositions` | object (7 keys) |
| `schema_version` | int |
| `search_budget` | object (3 keys) |
| `selection_rule` | str |
| `status` | str |
