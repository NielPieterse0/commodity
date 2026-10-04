<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/issue465-block1-controller-v3-expert-paths-manifest.json -->

# Issue465 Block1 Controller V3 Expert Paths Manifest

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue465-block1-controller-v3-expert-paths-manifest.json`

## Overview

| Field | Value |
| --- | --- |
| `block_id` | block-001 |
| `canonical_history_sha256` | 28648a0102d0a54e9dbde04ea60d2a2a3bb6c08fcd213a1385ec158011a9021f |
| `full_native_horizon_for_every_decision` | true |
| `future_calendar_semantics` | known Block1 decision dates then synthetic UTC business-day continuation; no later-block market data |
| `history_max_trade_date` | 2010-12-31 00:00:00+00:00 |
| `issue` | 465 |
| `kronos_model_checkpoint_sha256` | abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83 |
| `kronos_model_revision` | 2b554741eca47781b64468546e77fef3e85130e6 |
| `kronos_source_revision` | 67b630e67f6a18c9e9be918d9b4337c960db1e9a |
| `kronos_tokenizer_checkpoint_sha256` | 59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee |
| `kronos_tokenizer_revision` | 0e0117387f39004a9016484a186a908917e22426 |
| `later_block_market_data_accessed` | false |
| `maximum_native_horizon_sessions` | 20 |
| `ohlcv_history_sha256` | 8a49b1942d715643afc99ef04412f0a3dc08bb0bb4db13dc71b241c2df0b4530 |
| `output_sha256` | f71fe3c9ec7a8bb2863caf33710f9532ae780cf9bc531e907d080111d2b7979b |
| `pit_state_sha256` | ba91a8c4880a4427c34dc9b906d1bd4ce5670aeca45a297b26428c9bf00e81c2 |
| `protected_confirmation_accessed` | false |
| `row_count` | 123 |
| `schema_version` | 1 |
| `selection_use` | horizon_specific_direction_and_comparable_state_context |
| `timesfm_checkpoint_sha256` | 2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8 |
| `timesfm_model` | google/timesfm-2.5-200m-pytorch |
| `timesfm_revision` | 1d952420fba87f3c6dee4f240de0f1a0fbc790e3 |
| `timesfm_source_revision` | 3dae50b20d7a724981e8ea36cda75578f80dd2dc |

## Structure

| Field | Shape |
| --- | --- |
| `block_id` | str |
| `canonical_history_sha256` | str |
| `full_native_horizon_for_every_decision` | bool |
| `future_calendar_semantics` | str |
| `history_max_trade_date` | str |
| `issue` | int |
| `kronos_inference_profile` | object (3 keys) |
| `kronos_model_checkpoint_sha256` | str |
| `kronos_model_revision` | str |
| `kronos_source_revision` | str |
| `kronos_tokenizer_checkpoint_sha256` | str |
| `kronos_tokenizer_revision` | str |
| `later_block_market_data_accessed` | bool |
| `maximum_native_horizon_sessions` | int |
| `ohlcv_history_sha256` | str |
| `output_sha256` | str |
| `pit_state_sha256` | str |
| `protected_confirmation_accessed` | bool |
| `row_count` | int |
| `schema_version` | int |
| `selection_use` | str |
| `timesfm_checkpoint_sha256` | str |
| `timesfm_model` | str |
| `timesfm_revision` | str |
| `timesfm_source_revision` | str |
