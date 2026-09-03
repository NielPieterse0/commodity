<!-- GENERATED FILE. DO NOT EDIT. Source: research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/experiments/005-databento-history-redesign-279/exploratory-result.json -->

# commodity-ng

Source: `research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/experiments/005-databento-history-redesign-279/exploratory-result.json`

## Overview

| Field | Value |
| --- | --- |
| `schema_version` | 2 |
| `run_id` | databento-history-redesign-279 |
| `programme_id` | commodity-ng |
| `research_line_id` | line-next-defensible-edge |
| `gap` | The programme owns broad Henry Hub futures history from June 2010, but prior research asked whether that history could satisfy one frozen experiment. #279 reverses the question: identify what scientifically coherent experiments the owned history can support as it actually exists. |
| `mechanism` | Natural-gas curve shape carries storage/convenience-yield and regime information. Expiry-ranked nearby contracts can test curve dynamics using consistent electronic-trade-bar semantics even where official final-settlement semantics are historically incomplete, with source/economic regimes represented explicitly in robustness analysis. |
| `programme_conclusion` | GO to #285 as a literature-anchored exploratory replication programme using the full 2010+ Databento archive. #279 establishes that the data is broad enough to test market findings under its actual semantics; it does not establish an edge and does not reopen #271/#273. #285 must inspect development outcomes, tune economically and literature-justified constructions transparently, and first treat failure to reproduce published findings as a possible data, implementation or design error. Freeze only the final selected candidate before untouched confirmation. |
| `promotion_decision` | continue |

## Structure

| Field | Shape |
| --- | --- |
| `schema_version` | int |
| `run_id` | str |
| `programme_id` | str |
| `research_line_id` | str |
| `lifecycle` | array (15 items) |
| `orientation` | object (4 keys) |
| `gap` | str |
| `zoom_in` | object (2 keys) |
| `literature_snapshot_ref` | object (2 keys) |
| `mechanism` | str |
| `hypotheses` | object (2 keys) |
| `expectations` | object (2 keys) |
| `feasibility` | object (2 keys) |
| `execution` | object (2 keys) |
| `verification` | object (2 keys) |
| `comparison` | object (2 keys) |
| `external_triangulation` | object (2 keys) |
| `programme_conclusion` | str |
| `revisit_triggers` | array (1 items) |
| `promotion_decision` | str |
| `lineage` | object (2 keys) |
