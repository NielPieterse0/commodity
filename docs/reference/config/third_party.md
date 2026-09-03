<!-- GENERATED FILE. DO NOT EDIT. Source: config/third_party.json -->

# Third Party

Source: `config/third_party.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `policy_id` | commodity-third-party-v1 |
| `external_model_rule` | External model repositories may be used only through bounded adapters; enablement, model pins and runtime settings belong to config/models.json. |
| `licensing_rule` | Licensed raw market values stay out of Git unless terms explicitly permit repository storage; private research rights do not imply redistribution rights. |
| `source_status_owner` | config/data_sources.json |
| `execution_permission_owner` | config/trading-policy.json |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `policy_id` | str |
| `trust_classes` | object (4 keys) |
| `research_source_families` | object (5 keys) |
| `technical_sources` | array (8 items) |
| `external_model_rule` | str |
| `licensing_rule` | str |
| `source_status_owner` | str |
| `execution_permission_owner` | str |
