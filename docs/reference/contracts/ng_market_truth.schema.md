<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/ng_market_truth.schema.json -->

# Development-only NG market truth source attestation

Source: `contracts/ng_market_truth.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/ng_market_truth.schema.json |
| `title` | Development-only NG market truth source attestation |
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
| `required` | array (7 items) |
| `properties` | object (7 keys) |
| `$defs` | object (4 keys) |

## Contract

Required fields: `schema_version`, `evidence_class`, `protected_confirmation_accessed`, `dataset`, `product_code`, `max_trade_date`, `inputs`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `evidence_class` | constraint |
| `protected_confirmation_accessed` | constraint |
| `dataset` | constraint |
| `product_code` | constraint |
| `max_trade_date` | string |
| `inputs` | object |
