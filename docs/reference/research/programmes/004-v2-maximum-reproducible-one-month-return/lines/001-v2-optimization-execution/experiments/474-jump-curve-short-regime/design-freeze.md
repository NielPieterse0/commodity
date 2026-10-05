<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/474-jump-curve-short-regime/design-freeze.json -->

# 004-v2-maximum-reproducible-one-month-return

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/474-jump-curve-short-regime/design-freeze.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 474 |
| `freeze_id` | issue474-blocks2-4-ab-freeze-v1 |
| `status` | FROZEN_BEFORE_BLOCKS_2_4 |
| `programme_id` | 004-v2-maximum-reproducible-one-month-return |
| `research_line_id` | 001-v2-optimization-execution |
| `experiment_id` | 474-jump-curve-short-regime |
| `program_handoff_id` | block1-v3-edge-discovery-post470 |
| `source_generation` | e3e221b3c9d945813e92cef9dbef8fd0 |
| `landed_post470_main_sha` | 0fd0acf1415d2174c842ff0f3f8c30f13748f448 |
| `north_star` | Identify a causal, after-cost, execution-robust short-vs-flat edge mechanism and freeze the smallest architecture that survives untouched chronological research-OOS. |
| `post_warmup_semantics` | The Block-1 post-warmup A/B diagnostic starts flat after the first 30 decision rows; the full-block path may carry a pre-warmup position across that boundary. This convention is frozen and not normalized after results. |
| `runner_sha256` | 369e7750777d95d1369a2a76b1e8cba426859f7b6576a12304bf1ab1d0b5ab0a |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `freeze_id` | str |
| `status` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `experiment_id` | str |
| `program_handoff_id` | str |
| `source_generation` | str |
| `landed_post470_main_sha` | str |
| `source_generation_binding` | object (9 keys) |
| `pre_oos_implementation_evidence` | object (6 keys) |
| `exploratory_source_package` | object (7 keys) |
| `material_post470_exploratory_bindings` | object (12 keys) |
| `scientific_boundary` | object (5 keys) |
| `north_star` | str |
| `candidate_A` | object (2 keys) |
| `candidate_B` | object (3 keys) |
| `observable_state` | object (7 keys) |
| `execution_contract` | object (7 keys) |
| `block_contract` | object (4 keys) |
| `p0_p9_accounting` | object (10 keys) |
| `block1_frozen_economics_1p5` | object (2 keys) |
| `post_warmup_semantics` | str |
| `notable_edge_gate` | object (11 keys) |
| `candidate_B_extra_promotion_gate` | object (4 keys) |
| `terminal_dispositions` | array (3 items) |
| `stop_and_no_rescue_rules` | array (6 items) |
| `runner_sha256` | str |
