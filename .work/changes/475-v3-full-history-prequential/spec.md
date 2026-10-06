# Change Specification: V3 Full-History Prequential

- **Change ID**: `475-v3-full-history-prequential`
- **Status**: Active
- **Work item**: `WORK-475` / GitHub issue `#475`
- **Complexity**: large
- **Risk triggers**: architecture boundary, persistent state

## Outcome

Implement the repository mechanics required by #475 for one governed pre-2023 chronological prequential V3 research traversal, while keeping protected 2023+ evidence unopened.

## Scientific authority

The scientific design is owned by GitHub issue #475 and Programme 004 authority. This change does not redefine that design. Repository mappings are:

- Programme line: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json`
- Inference ledger: `research/programmes/004-v2-maximum-reproducible-one-month-return/inference-ledger.json`
- Decisions: `research/programmes/004-v2-maximum-reproducible-one-month-return/decisions.json`
- Protected-window registry: `research/programmes/004-v2-maximum-reproducible-one-month-return/sealed-windows.json`
- #475 experiment: `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/experiments/475-full-history-adaptive-edge/`

## Repository requirements

1. Add a reusable prequential engine that enforces `outcome_available_at < decision_time`, immutable prior decisions, a 252-row initialization, fixed fast/slow adaptation cadences, causal rolling/expanding evidence, and a bounded parent/child candidate tree.
2. Preserve permanent flat, always-short, trend-short, curve-short, trend+curve-short and legacy-V3 reference lanes, plus bounded model/risk-veto challengers and a negative control.
3. Score every candidate under base and severe execution and retain zero-weight failed challengers rather than deleting them mid-run.
4. Evaluate recurrence, parent-relative severe edge, leave-best-period concentration, drawdown and multiplicity before declaring a passing architecture; choose the smallest passing architecture.
5. Bind frozen market/session and retrospective TimesFM/Kronos development features by exact hash and enforce their PIT timestamps.
6. Register the physically present 2023+ Databento reserve by raw-byte identity without decoding protected outcomes; hard-fail any #475 access to that reserve.
7. Require a committed, clean design freeze that binds engine, runner, input, protected-registry and Programme 004 authority hashes before the authoritative traversal can start.
8. Persist chronological decision, learning, specialist-evidence, candidate, robustness, edge-attribution and future-invariance artifacts.

## Acceptance evidence

- `tests/test_issue475_full_history_prequential_v3.py`
- `scripts/research/run_issue475_full_history_prequential_v3.py preflight`
- Programme inference integrity and experiment-schema checks
- Full adversarial future-invariance proof during the authoritative traversal
- KIS change workflow and repository verification before promotion

## Explicit boundaries

- Pre-2023 #475 evidence is exploratory/consumed research evidence, not pristine confirmation.
- The `current_v3` lane is an explicitly labeled full-history legacy directional reference, not a false claim of exact replay of the Block-1-only 96-candidate meta-controller.
- Fundamentals remain held in this runner because no complete bound full-history PIT source is admitted here; seasonality has no standalone directional rule without a predeclared mechanism.
- No 2023+ decoding, scoring, visualization, threshold selection or redesign is allowed in this change.
