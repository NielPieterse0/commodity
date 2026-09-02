<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/research_metrics.schema.json -->

# Commodity Longitudinal Research Metrics Ledger

Source: `contracts/research_metrics.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/research-metrics/v1 |
| `title` | Commodity Longitudinal Research Metrics Ledger |
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
| `$defs` | object (7 keys) |

## Contract

Required fields: `schema_version`, `ledger_id`, `comparison_policy`, `stages`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | integer |
| `ledger_id` | string |
| `comparison_policy` | constraint |
| `stages` | array |
