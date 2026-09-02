<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/prereg.schema.json -->

# Commodity Confirmatory Preregistration

Source: `contracts/prereg.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/prereg/v1 |
| `title` | Commodity Confirmatory Preregistration |
| `type` | object |
| `additionalProperties` | false |

## Structure

| Field | Shape |
| --- | --- |
| `$schema` | str |
| `$id` | str |
| `title` | str |
| `type` | str |
| `additionalProperties` | bool |
| `required` | array (30 items) |
| `properties` | object (30 keys) |

## Contract

Required fields: `schema_version`, `experiment_id`, `programme_id`, `research_line_id`, `slice_id`, `orientation`, `evidence_scan_ref`, `literature_snapshot_ref`, `parent_question`, `uncertainty_reduced`, `outside_scope`, `mechanism`, `hypotheses`, `expectations`, `post_result_triangulation`, `mepi`, `forecast`, `datasets`, `dependence`, `power`, `features`, `model`, `evaluation`, `inference_ledger_entry_id`, `sealed_window`, `coherence_triggers`, `outcome_logic`, `permitted_human_dispositions`, `reproduction`, `lineage`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `experiment_id` | string |
| `programme_id` | string |
| `research_line_id` | string |
| `slice_id` | string |
| `orientation` | object |
| `evidence_scan_ref` | object |
| `literature_snapshot_ref` | object |
| `parent_question` | string |
| `uncertainty_reduced` | string |
| `outside_scope` | array |
| `mechanism` | string |
| `hypotheses` | object |
| `expectations` | object |
| `post_result_triangulation` | object |
| `mepi` | object |
| `forecast` | object |
| `datasets` | array |
| `dependence` | object |
| `power` | object |
| `features` | object |
| `model` | object |
| `evaluation` | object |
| `inference_ledger_entry_id` | string |
| `sealed_window` | object |
| `coherence_triggers` | array |
| `outcome_logic` | object |
| `permitted_human_dispositions` | array |
| `reproduction` | object |
| `lineage` | object |
