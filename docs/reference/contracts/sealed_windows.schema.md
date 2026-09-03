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
| `required` | array (4 items) |
| `properties` | object (4 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `windows`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `windows` | array |
| `zoom_level` | constraint |
| `programme_id` | string |
