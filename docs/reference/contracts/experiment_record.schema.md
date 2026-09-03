<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/experiment_record.schema.json -->

# Commodity Durable 15-Step Experiment Record v3

Source: `contracts/experiment_record.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/experiment-record/v3 |
| `title` | Commodity Durable 15-Step Experiment Record v3 |
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
| `required` | array (9 items) |
| `properties` | object (9 keys) |
| `$defs` | object (19 keys) |

## Contract

Required fields: `schema_version`, `programme_id`, `research_line_id`, `experiment_id`, `lineage`, `workflow`, `decisions`, `recommendations`, `open_questions`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `experiment_id` | string |
| `workflow` | array |
| `decisions` | array |
| `recommendations` | array |
| `open_questions` | array |
| `programme_id` | string |
| `research_line_id` | string |
| `lineage` | object |
