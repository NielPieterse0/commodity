<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue465-prereg-v1.json -->

# Issue465 Prereg V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue465-prereg-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 465 |
| `evidence_class` | development_only |
| `scope` | first_chronological_six_month_block_only |
| `status` | frozen_before_issue465_block1_scoring |
| `claim_boundary` | adaptive_development_vertical_slice_no_confirmation_claim |
| `protected_confirmation_accessed` | false |
| `protected_start` | 2023-01-01T00:00:00Z |
| `memory_includes_expanding` | true |
| `nonactive_families_rule` | inventory_every_admissible_family_and_record_explicit_disposition; never silently drop |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `evidence_class` | str |
| `scope` | str |
| `status` | str |
| `claim_boundary` | str |
| `protected_confirmation_accessed` | bool |
| `protected_start` | str |
| `dependencies` | object (2 keys) |
| `block_contract` | object (10 keys) |
| `pit_contract` | object (7 keys) |
| `selection_contract` | object (6 keys) |
| `historical_reentry_rule` | object (3 keys) |
| `specialist_library` | array (17 items) |
| `sparse_pair_library` | array (8 items) |
| `policy_search_space` | object (9 keys) |
| `memory_windows_sessions` | array (7 items) |
| `memory_includes_expanding` | bool |
| `comparable_state_contract` | object (4 keys) |
| `adaptation_contract` | object (4 keys) |
| `oracle_contract` | object (4 keys) |
| `horizon_contract` | object (3 keys) |
| `position_state_contract` | array (7 items) |
| `execution_contract` | object (13 keys) |
| `first_block_active_families` | array (13 items) |
| `nonactive_families_rule` | str |
| `source_identity_contract` | object (7 keys) |
| `pre_scoring_revision` | object (5 keys) |
| `required_outputs` | array (9 items) |
| `freeze_rules` | object (5 keys) |
