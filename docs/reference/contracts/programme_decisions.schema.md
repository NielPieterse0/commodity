<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/programme_decisions.schema.json -->

# Programme Decisions.Schema

Source: `contracts/programme_decisions.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/programme-decisions/v1 |
| `type` | object |
| `additionalProperties` | false |

## Structure

| Field | Shape |
| --- | --- |
| `$schema` | str |
| `$id` | str |
| `type` | str |
| `additionalProperties` | bool |
| `required` | array (3 items) |
| `properties` | object (3 keys) |

## Contract

Required fields: `schema_version`, `generated_projection`, `decisions`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `generated_projection` | constraint |
| `decisions` | array |
