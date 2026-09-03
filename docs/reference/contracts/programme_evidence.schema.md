<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/programme_evidence.schema.json -->

# Commodity Programme Evidence and Feasibility Map v2

Source: `contracts/programme_evidence.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/programme-evidence/v2 |
| `title` | Commodity Programme Evidence and Feasibility Map v2 |
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
| `required` | array (8 items) |
| `properties` | object (12 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `current_scan_id`, `refresh_triggers`, `research_line_refs`, `feasibility_map`, `semantics`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `programme_id` | string |
| `current_scan_id` | string |
| `previous_scan_id` | string / null |
| `retrospective_synthesis` | object |
| `refresh_triggers` | array |
| `current_helicopter_view` | object |
| `feasibility_map` | array |
| `reopening_gates` | object |
| `semantics` | object |
| `zoom_level` | constraint |
| `research_line_refs` | array |
