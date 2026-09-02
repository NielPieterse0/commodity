<!-- GENERATED FILE. DO NOT EDIT. Source: config/models.json -->

# Models

Source: `config/models.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `default_model` | ridge |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `default_model` | str |
| `models` | object (6 keys) |
| `kronos_confirmation_profile` | object (6 keys) |

## Models

| Model | Enabled | Kind | Family | Architecture |
| --- | --- | --- | --- | --- |
| `naive` | true | baseline | linear_baseline | zero_return |
| `ridge` | true | sklearn | linear_baseline | ridge |
| `hist_gb` | true | sklearn | tree_boosting_baseline | hist_gradient_boosting |
| `kronos_mini` | true | optional_foundation_model | foundation_model | kronos_mini |
| `kronos_base` | false | optional_foundation_model | foundation_model | kronos_base |
| `kronos_small` | false | optional_foundation_model | foundation_model | kronos_small |
