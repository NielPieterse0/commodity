# Change Specification: Trading Decision System V0

- **Change ID**: `355-trading-decision-system-v0`
- **Status**: Implementation verification
- **Complexity**: `large`; risk triggers `money`, `persistent_state` per `scope.json`

## Outcome

Implement the repository interfaces required by the frozen Phase-1 authority without changing its scientific design.

## Authority and scope

- Scientific/L3 authority: GitHub issue #355, implementation-ready decision comment `5611074612`.
- Operator risk authority: GitHub issue #355 comment `5611031058`.
- Work handoff: `WORK-355`, contract fingerprint `fea017b6dfc72d52fecda04c456a85a40f2dfca2ab691f3c004b154c3e60e8cf`.
- Owned/shared/excluded paths and lifecycle classification: `scope.json`.

## Repository mapping

- `config/trading-policy.json`: operator-owned paper/simulation risk boundary and live-trading prohibition.
- `config/simulation.json`: Phase-1 decision-system execution/cost contract and required run assumptions.
- `config/models.json`: enabled simple forecast ladder; no foundation-model dependency.
- `src/commodity/trading_decision_v0.py`: roll-safe target, walk-forward forecasts, signal translation, execution/risk ledger.
- `src/commodity/cli.py`: one-command `trading-decision-v0` orchestration and deterministic run identity.
- `tests/test_trading_decision_v0.py` and `tests/repository/test_cli.py`: executable acceptance evidence.

## Acceptance and boundaries

Acceptance is the `WORK-355` criteria plus current KIS verification/review obligations. Protected confirmation remains unopened; this change establishes executable benchmark machinery only and makes no trading-edge claim. Material changes to target, horizon, PIT semantics, roll semantics, or research design must return to L3 rather than being solved here.
