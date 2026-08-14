# V1 Research Completion — Phase 0 Merge-Gate Specification

Program: GitHub issue #15. Phase 0: #16. External review records: #22 and #23.

## Goal
Close every merge-blocking external-review finding with executable enforcement, regression tests, and fresh evidence before Phase A behavior begins.

## Gate
Part 1: #1–#6 and #17. Part 2: A1, A2, A4, F1, H1, K1.

## Required outcomes
- Roll-policy semantics have one authoritative owner and every declared semantic is consumed or rejected by implementation.
- Canonical per-contract market rows can feed the PIT research-dataset path; canonical mode cannot silently use the bootstrap proxy.
- PIT as-of joins cannot mix independent series/entities; grouping is explicit and validated.
- Recorded dependency-lock identity corresponds to the dependency set CI/bootstrap actually installs.
- Config resolution works for installed distributions without depending on the source-tree layout.
- Walk-forward configuration must leave a non-empty OOS period for the verified canonical-history boundary.
- The existing Databento full-history acquisition is quarantined; no paid reacquisition occurs in this program.
- Databento integrity/verification status is authoritative, explicit, and blocks research/canonical evidence promotion while incomplete.
- Tournament results include time-series-aware paired uncertainty/significance versus the configured baseline.
- Leakage controls test the full forecast path rather than one first prediction and are represented in emitted experiment records.
- LIVE mode requires explicit human approval evidence in addition to a boolean permission switch; default remains prohibited.

## Non-goals
No new paid data acquisition. No provider winner-takes-all decision. No LIVE authorization. No Kronos or Europe/Norway implementation in Phase 0.
