<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/002-henry-hub-fresh/experiment-designs.json -->

# 002-henry-hub-fresh

Source: `research/programmes/002-henry-hub-fresh/experiment-designs.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 1 |
| `level` | L3-development-design |
| `programme_id` | 002-henry-hub-fresh |
| `status` | unfrozen_development_designs_feasibility_classified |
| `empirical_execution_authority` | false |
| `preregistration_authority` | false |
| `confirmation_authority` | false |
| `operator_gate` | These are executable-quality scientific designs, not preregistrations. No design may be frozen, sealed, executed on protected evidence, or promoted to confirmation without a separate explicit operator authorization after feasibility and implementation verification. |
| `scientific_boundary` | Only external literature claims are being translated into tests. No legacy internal result is used as scientific evidence, calibration target, or expected outcome. |
| `next_gate` | All five prior REDESIGN defects have been converted into source-coherent GO designs or a prerequisite HOLD. Current feasibility is 14 GO / 7 HOLD / 0 REDESIGN. Implement and verify GO machinery without empirical literature-result execution; HOLD releases remain governed by revisit-triggers.json and any empirical/freeze transition remains operator-gated. |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `level` | str |
| `programme_id` | str |
| `status` | str |
| `empirical_execution_authority` | bool |
| `preregistration_authority` | bool |
| `confirmation_authority` | bool |
| `operator_gate` | str |
| `scientific_boundary` | str |
| `global_rules` | object (13 keys) |
| `designs` | array (21 items) |
| `coverage` | object (4 keys) |
| `next_gate` | str |
