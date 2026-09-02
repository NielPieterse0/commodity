<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/experiment_record.schema.json -->

# Commodity Durable Experiment Record

Source: `contracts/experiment_record.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/experiment-record/v1 |
| `title` | Commodity Durable Experiment Record |
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
| `required` | array (11 items) |
| `properties` | object (11 keys) |
| `$defs` | object (3 keys) |

## Contract

Required fields: `schema_version`, `experiment_id`, `orientation`, `context`, `frozen_setup`, `outcome`, `learning`, `programme_consequence`, `decisions`, `recommendations`, `open_questions`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `experiment_id` | string |
| `orientation` | string |
| `context` | object |
| `frozen_setup` | constraint |
| `outcome` | object |
| `learning` | string |
| `programme_consequence` | string |
| `decisions` | array |
| `recommendations` | array |
| `open_questions` | array |
