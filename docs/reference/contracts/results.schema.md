<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/results.schema.json -->

# Commodity Confirmatory Results

Source: `contracts/results.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/results/v1 |
| `title` | Commodity Confirmatory Results |
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
| `required` | array (16 items) |
| `properties` | object (16 keys) |

## Contract

Required fields: `schema_version`, `experiment_id`, `run_id`, `prereg_sha256`, `code`, `data`, `features`, `model`, `environment`, `raw_evidence`, `verification`, `method_compliance`, `scientific_evidence`, `coherence`, `family_inference`, `artifacts`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `experiment_id` | string |
| `run_id` | string |
| `prereg_sha256` | string |
| `code` | object |
| `data` | object |
| `features` | object |
| `model` | object |
| `environment` | object |
| `raw_evidence` | object |
| `verification` | array |
| `method_compliance` | enum |
| `scientific_evidence` | enum |
| `coherence` | object |
| `family_inference` | object / null |
| `artifacts` | array |
