<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/research_line.schema.json -->

# Commodity Research Line

Source: `contracts/research_line.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/research-line/v1 |
| `title` | Commodity Research Line |
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
| `required` | array (17 items) |
| `properties` | object (19 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `research_line_id`, `legacy_research_line_ids`, `status`, `big_picture`, `why_zoomed_in`, `tested_role_target_horizon`, `historical_facts`, `useful_secondary_observations`, `remaining_untested_roles`, `revisit_trigger`, `programme_interpretation`, `evidence_refs`, `experiment_history`, `experiment_refs`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `zoom_level` | constraint |
| `programme_id` | string |
| `research_line_id` | string |
| `legacy_research_line_ids` | array |
| `status` | string |
| `selection_basis` | string |
| `stopping_rules` | object |
| `big_picture` | string |
| `why_zoomed_in` | string |
| `tested_role_target_horizon` | string |
| `historical_facts` | object |
| `useful_secondary_observations` | array |
| `remaining_untested_roles` | array |
| `revisit_trigger` | string |
| `programme_interpretation` | string |
| `evidence_refs` | array |
| `experiment_history` | array |
| `experiment_refs` | array |
