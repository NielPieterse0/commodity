# Change Specification: #89 V2 model criticism

- **Change ID**: `089-v2-model-criticism-review`
- **Status**: Active
- **Complexity**: medium

## Outcome

Complete #89 from frozen evidence only: diagnose the completed research design, separate interpretation from future hypotheses, record retained/revised/retired assumptions, and capture any next experiments separately without executing them.

## Authority and scope

- Authoritative sources: #78 longitudinal ledger, Phase-D closeout/diagnostics, #83 empirical closeout, #180 corrected Kronos result, #81/#84/#85 frozen contracts, #88 recommendation audit.
- Owned paths: `docs/development/v2-model-criticism/**` and this change record.
- Excluded: empirical artifacts, configs, model/data code, new data acquisition or fitting.
- Work record: `RES-89`.

## Requirements

- **REQ-001**: Review all material assumptions listed by #89 against frozen evidence.
- **REQ-002**: Never invent #83/#84/#85 performance where no valid run exists.
- **REQ-003**: Separate observed-result interpretation from adaptive next-experiment design.
- **REQ-004**: Every recommended new target/input/model/data test must have its own future issue and fresh confirmation rule.
