<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-012-physical-balance-drivers/literature-reproduction.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/rep-012-physical-balance-drivers/literature-reproduction.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `design_id` | rep-012-physical-balance-drivers |
| `issue` | 327 |
| `programme_id` | 002-henry-hub-fresh |
| `research_line_id` | 005-fundamental-balance |
| `zoom_level` | L5 |
| `literature_gate_closed` | true |
| `literature_disposition` | ROBERTS_BROWN_YUCEL_SOURCE_PERIOD_PHYSICAL_CONTROLS_REPRODUCED_WITH_REGIME_BREAK |
| `replication_class_target` | source_faithful_replication_then_independent_mechanism_extension |
| `replication_class_achieved` | exact_public_roberts_replication_python_translation |
| `method` | Independent Python implementation of the exact Roberts Stata Johansen/VECM design using the governed prepared dataset. VAR lag order 5 gives four lagged differences; an unrestricted constant is included; source stationary controls enter contemporaneously exactly as sindicators(); Stata if-qualifier semantics retain pre-boundary lag context for the post-2007 sample. |
| `source_claim` | A rank-one long-run Henry Hub/WTI relationship exists in the 1997-2007 Brown-Yucel period, primarily adjusted through natural-gas prices; the relationship disappears in the full and post-2007 samples, while stationary gas-market controls strengthen source-period cointegration evidence. |
| `interpretation` | Roberts (2019) is independently reproduced from the exact public package in Python. The Brown-Yucel 1997-2007 source period has rank-one Henry Hub/WTI cointegration, Henry Hub performs the dominant error correction, and Roberts Table 6 physical controls reproduce: cold and cooling-degree surprises are positive/highly significant while storage above its five-year norm is significantly negative, reducing the Henry Hub equation residual standard error from about 0.081 to 0.077. The long-run oil-gas relationship is not supported in the full or post-2007 samples, confirming Roberts' structural-break conclusion. This closes the source-faithful rep-012 literature gate for the weather/storage physical-control mechanism; production, consumption, power and LNG remain outside this source and require separate evidence. |
| `forecast_translation_role` | not_run; historical source-period physical-control reproduction does not authorize direct modern predictive translation after the documented regime break |
| `protected_confirmation_accessed` | false |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `design_id` | str |
| `issue` | int |
| `programme_id` | str |
| `research_line_id` | str |
| `zoom_level` | str |
| `literature_gate_closed` | bool |
| `literature_disposition` | str |
| `replication_class_target` | str |
| `replication_class_achieved` | str |
| `source_study` | object (3 keys) |
| `source_package` | object (5 keys) |
| `method` | str |
| `source_claim` | str |
| `reproduction` | object (7 keys) |
| `core_checks` | object (7 keys) |
| `published_precision_matches` | object (3 keys) |
| `paper_table_discrepancies` | array (2 items) |
| `interpretation` | str |
| `forecast_translation_role` | str |
| `protected_confirmation_accessed` | bool |
| `table6_physical_balance` | object (4 keys) |
