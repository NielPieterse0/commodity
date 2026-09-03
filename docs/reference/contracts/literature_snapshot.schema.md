<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/literature_snapshot.schema.json -->

# Commodity Literature Snapshot

Source: `contracts/literature_snapshot.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/literature-snapshot/v1 |
| `title` | Commodity Literature Snapshot |
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

Required fields: `schema_version`, `snapshot_id`, `research_question`, `search_scope`, `sources`, `claim_map`, `expected_observations`, `disconfirming_observations`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `snapshot_id` | string |
| `research_question` | string |
| `search_scope` | string |
| `sources` | array |
| `claim_map` | array |
| `expected_observations` | array |
| `disconfirming_observations` | array |
