<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.json -->

# 003-natural-gas-trading-decision-system

Source: `research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 003-natural-gas-trading-decision-system |
| `phase` | 7 |
| `issue` | 361 |
| `status` | prospective_active |
| `protected_confirmation_accessed` | false |
| `claim_boundary` | historical development evidence remains non-confirmatory; fresh exact-source coverage and the pinned specialist runtime are verified, and only untouched decisions created strictly after the recorded activation timestamp and after this activation change lands on the registered default branch may count as prospective evidence |
| `live_capital_authorized` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `phase` | int |
| `issue` | int |
| `status` | str |
| `protected_confirmation_accessed` | bool |
| `freeze_landing` | object (4 keys) |
| `claim_boundary` | str |
| `frozen_candidate` | object (7 keys) |
| `prospective_execution` | object (10 keys) |
| `prospective_activation` | object (12 keys) |
| `prospective_serving_contract` | object (19 keys) |
| `bound_configuration_sha256` | object (5 keys) |
| `historical_evidence` | object (2 keys) |
| `prospective_evidence_contract` | object (11 keys) |
| `prospective_interpretation` | object (4 keys) |
| `decisions_and_assumptions` | array (3 items) |
| `live_capital_authorized` | bool |
