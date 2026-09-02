<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/sealed_windows.schema.json -->

# Commodity Sealed Confirmation Registry

Source: `contracts/sealed_windows.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/sealed-windows/v1 |
| `title` | Commodity Sealed Confirmation Registry |
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
| `required` | array (2 items) |
| `properties` | object (2 keys) |

## Contract

Required fields: `schema_version`, `windows`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `windows` | array |
