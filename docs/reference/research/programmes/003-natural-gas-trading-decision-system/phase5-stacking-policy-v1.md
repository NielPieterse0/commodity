<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/003-natural-gas-trading-decision-system/phase5-stacking-policy-v1.json -->

# 003-natural-gas-trading-decision-system

Source: `research/programmes/003-natural-gas-trading-decision-system/phase5-stacking-policy-v1.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `programme_id` | 003-natural-gas-trading-decision-system |
| `phase` | 5 |
| `issue` | 359 |
| `status` | complete_development_candidate_selected |
| `protected_confirmation_accessed` | false |
| `claim_boundary` | development_policy_selection_only_no_clean_confirmation_claim |
| `authority` | github-issue-359 |
| `preregistration_sha256` | 98e59ccb64d8e6df995239686793ce05487a7b8c2d0773f6dc7e85b836f87fab |
| `result_sha256` | fc2dee42b86020bc36e1bcc9a2aaaadba84545e3c290ea30f1e5e4f49ad917c9 |
| `programme_route` | phase5_complete_handoff_to_phase6_bounded_gap_investigation |
| `next_evidence_stage` | Phase 6 may consume exactly this candidate as its frozen comparator. Protected 2023+ confirmation remains sealed until its explicit gate. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `programme_id` | str |
| `phase` | int |
| `issue` | int |
| `status` | str |
| `protected_confirmation_accessed` | bool |
| `claim_boundary` | str |
| `authority` | str |
| `preregistration_sha256` | str |
| `result_sha256` | str |
| `evidence_boundary` | object (2 keys) |
| `selection_contract` | object (5 keys) |
| `nested_selection_path` | object (3 keys) |
| `selected_candidate` | object (8 keys) |
| `no_modifier_comparator` | object (5 keys) |
| `diagnostics` | object (9 keys) |
| `interpretation` | object (3 keys) |
| `programme_route` | str |
| `next_evidence_stage` | str |
