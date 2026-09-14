<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json -->

# 004-v2-maximum-reproducible-one-month-return

Source: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `zoom_level` | L2 |
| `programme_id` | 004-v2-maximum-reproducible-one-month-return |
| `research_line_id` | 001-v2-optimization-execution |
| `status` | active |
| `big_picture` | Execute Programme #393 as an auditable optimization campaign for reproducible one-month net trading return while preserving V1 and later evidence boundaries. |
| `why_zoomed_in` | Programme setup registered the variable/search design but did not execute optimization; issue #424 establishes the shared execution, scoring, and trial-accounting layer needed before family searches. |
| `tested_role_target_horizon` | Issue #424 tests the optimization harness itself on bounded pre-2023 development evidence; it does not select a V2 champion. |
| `revisit_trigger` | Revisit the harness contract if a registered variable cannot be represented without weakening PIT, chronological-selection, trial-accounting, or executable-cost semantics. |
| `programme_interpretation` | Issue #424 is infrastructure and bounded development pilot evidence only; later V2 execution slices must consume it without opening protected confirmation or prospective evidence. |
| `selection_basis` | Primary optimization objective is reproducible monthly net return after costs with mandatory risk, stability, concentration, and execution diagnostics. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `zoom_level` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `legacy_research_line_ids` | array (0 items) |
| `status` | str |
| `big_picture` | str |
| `why_zoomed_in` | str |
| `tested_role_target_horizon` | str |
| `historical_facts` | object (3 keys) |
| `useful_secondary_observations` | array (1 items) |
| `remaining_untested_roles` | array (6 items) |
| `revisit_trigger` | str |
| `programme_interpretation` | str |
| `evidence_refs` | array (5 items) |
| `experiment_history` | array (1 items) |
| `experiment_refs` | array (0 items) |
| `selection_basis` | str |
| `stopping_rules` | object (1 keys) |
