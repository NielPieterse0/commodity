<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-source-feasibility-v2.json -->

# Issue448 Source Feasibility V2

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-source-feasibility-v2.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 448 |
| `programme_issue` | 393 |
| `plan_id` | issue448-source-feasibility-v2 |
| `status` | registered_before_issue448_empirical_scoring |
| `evidence_class` | development_source_feasibility |
| `latest_allowed_trade_date` | 2022-12-31 |
| `protected_confirmation_accessed` | false |
| `decision` | Proceed with technical, market-structure/OI and event-timing implementation; keep true storage surprise on HOLD; perform options zero-spend feasibility only and do not let it block V2. |
| `protected_evidence_statement` | No confirmation, prospective paper, SIM, LIVE, or post-2022 outcome evidence was inspected to make these source decisions. |
| `supersedes` | issue448-source-feasibility-v1 |
| `supersession_reason` | No-scoring full-history preflight resolved actual nested OI coverage and justified the preregistered availability-aligned OI evaluation lane before empirical scoring. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `programme_issue` | int |
| `plan_id` | str |
| `status` | str |
| `evidence_class` | str |
| `latest_allowed_trade_date` | str |
| `protected_confirmation_accessed` | bool |
| `preregistration_ref` | object (2 keys) |
| `sources` | object (7 keys) |
| `gates` | object (5 keys) |
| `decision` | str |
| `protected_evidence_statement` | str |
| `supersedes` | str |
| `supersession_reason` | str |
| `open_interest_nested_coverage_feasibility` | object (6 keys) |
