<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/research_backlog.schema.json -->

# Research Backlog.Schema

Source: `contracts/research_backlog.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/research-backlog/v1 |
| `type` | object |
| `additionalProperties` | false |

## Structure

| Field | Shape |
| --- | --- |
| `$schema` | str |
| `$id` | str |
| `type` | str |
| `additionalProperties` | bool |
| `required` | array (5 items) |
| `properties` | object (5 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `programme_id`, `generated_projection`, `items`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `generated_projection` | constraint |
| `items` | array |
| `zoom_level` | constraint |
| `programme_id` | string |
