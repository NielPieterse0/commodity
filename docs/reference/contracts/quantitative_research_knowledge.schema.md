<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/quantitative_research_knowledge.schema.json -->

# Commodity quantitative research knowledge router

Source: `contracts/quantitative_research_knowledge.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/quantitative_research_knowledge.schema.json |
| `title` | Commodity quantitative research knowledge router |
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
| `required` | array (15 items) |
| `properties` | object (15 keys) |
| `$defs` | object (7 keys) |

## Contract

Required fields: `schema_version`, `router_id`, `programme_issue`, `phase_issue`, `purpose`, `canonical_methodology_owner`, `agent_usage`, `sources`, `routing`, `playbooks`, `methodology_map`, `missing_controls`, `legacy_inputs`, `copyright_policy`, `protected_confirmation_boundary`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `router_id` | string |
| `programme_issue` | constraint |
| `phase_issue` | constraint |
| `purpose` | string |
| `canonical_methodology_owner` | constraint |
| `agent_usage` | object |
| `sources` | object |
| `routing` | object |
| `playbooks` | object |
| `methodology_map` | array |
| `missing_controls` | array |
| `legacy_inputs` | array |
| `copyright_policy` | object |
| `protected_confirmation_boundary` | constraint |
