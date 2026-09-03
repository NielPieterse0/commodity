<!-- GENERATED FILE. DO NOT EDIT. Source: config/research_methodology.json -->

# literature-anchored-research-lifecycle-v3

Source: `config/research_methodology.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 3 |
| `methodology_id` | literature-anchored-research-lifecycle-v3 |
| `issue` | 300 |
| `supersedes_issue` | 273 |
| `status` | active_for_new_research_after_merge |
| `new_exploratory_schema_version` | 3 |
| `literature_snapshot_contract` | contracts/literature_snapshot.schema.json |
| `revisit_trigger_registry` | research/programmes/001-commodity-natural-gas/revisit-triggers.json |
| `dataset_reconstruction_verification_method` | deterministic_rebuild_exact_comparison |
| `dataset_semantic_verification_method` | explicit_dataset_semantics_v1 |
| `execution_authority` | false |
| `trading_policy_owner` | config/trading-policy.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `methodology_id` | str |
| `issue` | int |
| `supersedes_issue` | int |
| `status` | str |
| `lifecycle_stages` | array (15 items) |
| `new_exploratory_schema_version` | int |
| `literature_snapshot_contract` | str |
| `revisit_trigger_registry` | str |
| `new_confirmatory_execution_requires` | array (10 items) |
| `new_exploratory_execution_requires` | array (4 items) |
| `dataset_reconstruction_verification_method` | str |
| `dataset_semantic_verification_method` | str |
| `legacy_exploratory_schema_versions` | array (2 items) |
| `legacy_evidence` | object (8 keys) |
| `truth_classes` | array (3 items) |
| `evidence_levels` | array (7 items) |
| `human_dispositions` | array (6 items) |
| `execution_authority` | bool |
| `trading_policy_owner` | str |
| `research_hierarchy` | object (4 keys) |
| `zoom_level_contracts` | object (13 keys) |
| `governed_research_workflow` | array (15 items) |
| `governed_research_workflow_details` | array (15 items) |
