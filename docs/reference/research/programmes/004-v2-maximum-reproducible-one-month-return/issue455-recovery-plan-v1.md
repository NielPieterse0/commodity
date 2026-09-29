<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-recovery-plan-v1.json -->

# Issue455 Recovery Plan V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-recovery-plan-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 455 |
| `programme_issue` | 393 |
| `plan_id` | issue455-recovery-plan-v1 |
| `status` | preregistered_before_full_acquisition_and_replay |
| `evidence_class` | development |
| `claim_boundary` | recover effective #426 weather inputs and execute registered power x weather only after exact replay reproduction |
| `protected_confirmation_accessed` | false |
| `true_forward_accessed` | false |
| `paper_accessed` | false |
| `saxo_sim_accessed` | false |
| `saxo_live_accessed` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `plan_id` | str |
| `status` | str |
| `evidence_class` | str |
| `claim_boundary` | str |
| `protected_confirmation_accessed` | bool |
| `true_forward_accessed` | bool |
| `paper_accessed` | bool |
| `saxo_sim_accessed` | bool |
| `saxo_live_accessed` | bool |
| `authority` | object (9 keys) |
| `frozen_oracles` | object (3 keys) |
| `source_contract` | object (11 keys) |
| `anchors` | array (4 items) |
| `extraction_contract` | object (12 keys) |
| `allowed_archive_omission_reasons` | array (2 items) |
| `initial_source_probe` | object (6 keys) |
| `reproduction_policy` | object (4 keys) |
| `power_weather_gate` | object (5 keys) |
