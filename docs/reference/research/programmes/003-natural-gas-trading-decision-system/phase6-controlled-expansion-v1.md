<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/003-natural-gas-trading-decision-system/phase6-controlled-expansion-v1.json -->

# 003-natural-gas-trading-decision-system

Source: `research/programmes/003-natural-gas-trading-decision-system/phase6-controlled-expansion-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 003-natural-gas-trading-decision-system |
| `phase` | 6 |
| `issue` | 360 |
| `status` | complete |
| `protected_confirmation_accessed` | false |
| `preregistration_sha256` | 5876a7a7c8130ed66714577c4e17be52a03dee2e96ae68d23c24d6d32b8dc603 |
| `input_score_sha256` | 6e8fa002163600f54eae929724f2c1ae69606de72a9070a49d0e75ade2150f9f |
| `annual_refit_advances` | false |
| `decision` | reject_annual_refit_retain_frozen_phase5_cadence |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `phase` | int |
| `issue` | int |
| `status` | str |
| `protected_confirmation_accessed` | bool |
| `preregistration_sha256` | str |
| `input_score_sha256` | str |
| `candidate` | object (6 keys) |
| `frozen_two_year_cadence` | object (8 keys) |
| `annual_refit_candidate` | object (8 keys) |
| `decision_gates` | object (5 keys) |
| `annual_refit_advances` | bool |
| `decision` | str |
| `interpretation` | object (3 keys) |
