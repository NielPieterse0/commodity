<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/001-v1-next-session-return-baseline/line.json -->

# 001-commodity-natural-gas

Source: `research/programmes/001-commodity-natural-gas/lines/001-v1-next-session-return-baseline/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 001-commodity-natural-gas |
| `research_line_id` | 001-v1-next-session-return-baseline |
| `big_picture` | Establish an honest leakage-safe baseline before escalating model complexity. |
| `programme_interpretation` | Move from generic model search toward complementary, mechanism-led signal families and stronger controls. |
| `revisit_trigger` | Only revisit one-session return forecasting when a bounded mechanism or new information source changes the expected-information-value case. |
| `status` | rejected_by_evidence |
| `tested_role_target_horizon` | Naive/zero, Ridge and HistGB next-session log-return forecasting at a one-session horizon under expanding walk-forward evaluation. |
| `why_zoomed_in` | The programme needed to know whether daily market state, seasonality and PIT exogenous context could beat a simple zero-return control. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `zoom_level` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `legacy_research_line_ids` | array (1 items) |
| `big_picture` | str |
| `evidence_refs` | array (2 items) |
| `experiment_history` | array (1 items) |
| `historical_facts` | object (3 keys) |
| `programme_interpretation` | str |
| `remaining_untested_roles` | array (4 items) |
| `revisit_trigger` | str |
| `status` | str |
| `tested_role_target_horizon` | str |
| `useful_secondary_observations` | array (2 items) |
| `why_zoomed_in` | str |
| `experiment_refs` | array (1 items) |
