<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/programme.schema.json -->

# Commodity Research Programme

Source: `contracts/programme.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/programme/v1 |
| `title` | Commodity Research Programme |
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
| `required` | array (8 items) |
| `properties` | object (8 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `legacy_programme_ids`, `name`, `mission`, `status`, `line_refs`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `zoom_level` | constraint |
| `programme_id` | string |
| `legacy_programme_ids` | array |
| `name` | string |
| `mission` | string |
| `status` | enum |
| `line_refs` | array |
