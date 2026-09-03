<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/legacy_experiment_record.schema.json -->

# Commodity Legacy Experiment Record

Source: `contracts/legacy_experiment_record.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/legacy-experiment-record/v1 |
| `title` | Commodity Legacy Experiment Record |
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
| `required` | array (14 items) |
| `properties` | object (15 keys) |
| `$defs` | object (2 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `research_line_id`, `experiment_id`, `governance_generation`, `historical_status`, `summary`, `outcome`, `issue_lineage`, `source_artifacts`, `decisions`, `recommendations`, `open_questions`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `zoom_level` | constraint |
| `programme_id` | string |
| `research_line_id` | string |
| `experiment_id` | string |
| `governance_generation` | constraint |
| `historical_status` | enum |
| `summary` | string |
| `outcome` | string / null |
| `issue_lineage` | array |
| `source_artifacts` | array |
| `decisions` | array |
| `recommendations` | array |
| `open_questions` | array |
| `metrics_ledger_refs` | array |
