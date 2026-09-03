<!-- GENERATED FILE. DO NOT EDIT. Source: contracts/interpretation_metadata.schema.json -->

# Commodity Interpretation Metadata

Source: `contracts/interpretation_metadata.schema.json`

## Overview

| Field | Value |
| --- | --- |
| `$schema` | https://json-schema.org/draft/2020-12/schema |
| `$id` | https://commodity.local/contracts/interpretation-metadata/v3 |
| `title` | Commodity Interpretation Metadata |
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
| `required` | array (13 items) |
| `properties` | object (13 keys) |

## Contract

Required fields: `schema_version`, `zoom_level`, `experiment_id`, `prereg_sha256`, `results_sha256`, `human_disposition`, `observed_vs_expected`, `disconfirmers_observed`, `post_result_literature_snapshot_ref`, `external_triangulation`, `literature_expectation_assessment`, `coherence_interpretation`, `hierarchy_retrace`

| Property | Type / constraint |
| --- | --- |
| `schema_version` | constraint |
| `experiment_id` | string |
| `prereg_sha256` | string |
| `results_sha256` | string |
| `human_disposition` | enum |
| `observed_vs_expected` | string |
| `disconfirmers_observed` | array |
| `post_result_literature_snapshot_ref` | object |
| `external_triangulation` | string |
| `literature_expectation_assessment` | string |
| `coherence_interpretation` | string |
| `hierarchy_retrace` | object |
| `zoom_level` | constraint |
