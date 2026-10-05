<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/474-jump-curve-short-regime/family-inference.json -->

# Family Inference

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/474-jump-curve-short-regime/family-inference.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `issue` | 474 |
| `experiment_id` | 474-jump-curve-short-regime |
| `evidence_scope` | Block 1 development only |
| `status` | SELECTION_ADJUSTED_PROMOTION_AUTHORITY_WITHHELD |
| `source_generation` | e3e221b3c9d945813e92cef9dbef8fd0 |
| `purpose` | Close the P8 family-level inference gate without misrepresenting heavily searched Block-1 development evidence as independent confirmation. |
| `selection_adjusted_conclusion` | Block-1 returns, robustness perturbations, and attribution support mechanism discovery and candidate freezing only. They cannot independently establish statistical significance after the complete adaptive search history. The frozen candidate identity must earn promotion through chronological untouched Blocks 2-4 under the predeclared no-retuning rule. |
| `block1_evidence_role` | development_mechanism_discovery_not_independent_confirmation |
| `promotion_authority` | frozen_untouched_oos_only |
| `p8_gate` | PASS_AS_CLAIM_BOUNDARY_NOT_AS_SIGNIFICANCE_CLAIM |
| `no_rescue_rule` | No threshold, feature, holding, sizing, deadband, learned model, or state-definition change may be selected from Blocks 2-4 before the frozen A/B comparison is interpreted. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `issue` | int |
| `experiment_id` | str |
| `evidence_scope` | str |
| `status` | str |
| `source_generation` | str |
| `purpose` | str |
| `search_families_accounted_for` | array (13 items) |
| `dependence_and_multiplicity` | object (8 keys) |
| `selection_adjusted_conclusion` | str |
| `block1_evidence_role` | str |
| `promotion_authority` | str |
| `p8_gate` | str |
| `no_rescue_rule` | str |
