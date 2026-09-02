<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/programme_inference.schema.json -->

# Commodity Programme Inference Ledger

Source: `contracts/programme_inference.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/programme-inference/v1 |
| `title` | Commodity Programme Inference Ledger |
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

Required fields: `schema_version`, `programme_id`, `entries`, `family_inference`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `programme_id` | string |
| `entries` | array |
| `family_inference` | array |
