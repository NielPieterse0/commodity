<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-successor-baseline-plan-v1.json -->

# Issue455 Successor Baseline Plan V1

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue455-successor-baseline-plan-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 455 |
| `programme_issue` | 393 |
| `plan_id` | issue455-successor-baseline-plan-v1 |
| `status` | preregistered_before_successor_weather_scoring_and_power_weather_interaction |
| `evidence_class` | development |
| `decision` | replace_exact_issue426_recovery_as_prerequisite_with_a_new_reproducible_successor_weather_baseline |
| `rationale` | Exact historical temperatures are required only for an exact #426 reproduction claim. The current market inputs and weather feature builder reproduce their frozen identities, while the original #426 effective weather archive does not. Further archaeology is therefore not required before new development research. |
| `protected_confirmation_accessed` | false |
| `true_forward_accessed` | false |
| `prospective_paper_accessed` | false |
| `saxo_sim_accessed` | false |
| `saxo_live_accessed` | false |
| `claim_boundary` | development-only successor weather baseline and MISO power×weather marginal-value research; no confirmation or live-edge claim |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `plan_id` | str |
| `status` | str |
| `evidence_class` | str |
| `decision` | str |
| `rationale` | str |
| `historical_boundary` | object (4 keys) |
| `successor_weather_freeze` | object (11 keys) |
| `successor_weather_semantics` | object (8 keys) |
| `fixed_authorities` | object (8 keys) |
| `weather_baseline_experiment` | object (4 keys) |
| `power_weather_experiment` | object (6 keys) |
| `stopping_rules` | array (5 items) |
| `protected_confirmation_accessed` | bool |
| `true_forward_accessed` | bool |
| `prospective_paper_accessed` | bool |
| `saxo_sim_accessed` | bool |
| `saxo_live_accessed` | bool |
| `claim_boundary` | str |
