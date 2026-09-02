<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/revisit_triggers.schema.json -->

# Commodity Research Revisit Trigger Registry

Source: `contracts/revisit_triggers.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/revisit-triggers/v1 |
| `title` | Commodity Research Revisit Trigger Registry |
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
| `required` | array (4 items) |
| `properties` | object (4 keys) |

## Contract

Required fields: `schema_version`, `registry_id`, `triggers`, `evaluation_history`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `registry_id` | string |
| `triggers` | array |
| `evaluation_history` | array |
