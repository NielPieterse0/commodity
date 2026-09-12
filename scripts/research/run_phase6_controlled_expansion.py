from __future__ import annotations

import hashlib
import json
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from commodity.stacking_policy import select_policy_from_prior_oos

CHANGE = ROOT / ".work" / "changes" / "360-controlled-expansion"
SCORES = ROOT / ".work" / "changes" / "359-stacking-policy" / "phase5-results" / "policy-year-scores.csv"
PREREG = CHANGE / "phase6-preregistration.json"
RESULT = CHANGE / "phase6-controlled-expansion-result.json"
CANONICAL = ROOT / "research" / "programmes" / "003-natural-gas-trading-decision-system" / "phase6-controlled-expansion-v1.json"
EVAL_YEARS = tuple(range(2017, 2023))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_year(scores: pd.DataFrame, year: int, selected_id: str) -> dict[str, Any]:
    row = scores.loc[scores["config_id"].eq(selected_id) & scores["year"].eq(year)]
    if len(row) != 1:
        raise ValueError(f"expected one score row for {selected_id} in {year}")
    return row.iloc[0].to_dict()


def build_path(scores: pd.DataFrame, cadence: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if cadence == "annual":
        blocks = [(year, year) for year in EVAL_YEARS]
    elif cadence == "two_year":
        blocks = [(2017, 2018), (2019, 2020), (2021, 2022)]
    else:
        raise ValueError(f"unsupported cadence: {cadence}")
    for start, end in blocks:
        selected = select_policy_from_prior_oos(scores, outer_start_year=start)
        selected_id = str(selected["config_id"])
        for year in range(start, end + 1):
            score = _selected_year(scores, year, selected_id)
            rows.append({"year": year, "selected_config_id": selected_id, **score})
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows).sort_values("year")
    ids = frame["selected_config_id"].astype(str).tolist()
    return {
        "standard_net_pnl_usd": float(frame["net_pnl_usd"].sum()),
        "continuous_net_pnl_usd": float(frame["continuous_net_pnl_usd"].sum()),
        "median_yearly_net_pnl_usd": float(frame["net_pnl_usd"].median()),
        "worst_yearly_net_pnl_usd": float(frame["net_pnl_usd"].min()),
        "transaction_cost_usd": float(frame["transaction_cost_usd"].sum()),
        "max_yearly_drawdown_fraction": float(frame["max_drawdown_fraction"].max()),
        "selected_config_changes": sum(left != right for left, right in pairwise(ids)),
        "yearly_path": rows,
    }


def decide(baseline: dict[str, Any], annual: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    gates = {
        "net_pnl_noninferior": annual["standard_net_pnl_usd"] >= baseline["standard_net_pnl_usd"],
        "median_noninferior": annual["median_yearly_net_pnl_usd"] >= baseline["median_yearly_net_pnl_usd"],
        "worst_year_noninferior": annual["worst_yearly_net_pnl_usd"] >= baseline["worst_yearly_net_pnl_usd"],
        "cost_bounded": annual["transaction_cost_usd"] <= 1.25 * baseline["transaction_cost_usd"],
        "drawdown_noninferior": annual["max_yearly_drawdown_fraction"] <= baseline["max_yearly_drawdown_fraction"],
    }
    return all(gates.values()), gates


def main() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    scores = pd.read_csv(SCORES)
    scores["year"] = pd.to_numeric(scores["year"], errors="raise").astype(int)
    if int(scores["year"].max()) > 2022:
        raise ValueError("protected 2023+ scores are not permitted")
    baseline = summarize(build_path(scores, "two_year"))
    annual = summarize(build_path(scores, "annual"))
    expected = float(prereg["frozen_comparator"]["standard_net_pnl_usd"])
    if abs(baseline["standard_net_pnl_usd"] - expected) > 1e-9:
        raise ValueError("frozen Phase-5 comparator does not reproduce")
    advance, gates = decide(baseline, annual)
    result = {
        "schema_version": 1,
        "programme_id": prereg["programme_id"],
        "phase": 6,
        "issue": 360,
        "status": "complete",
        "protected_confirmation_accessed": False,
        "preregistration_sha256": _sha256(PREREG),
        "input_score_sha256": _sha256(SCORES),
        "candidate": prereg["candidate"],
        "frozen_two_year_cadence": baseline,
        "annual_refit_candidate": annual,
        "decision_gates": gates,
        "annual_refit_advances": advance,
        "decision": (
            "advance_annual_refit_as_phase6_contributor"
            if advance
            else "reject_annual_refit_retain_frozen_phase5_cadence"
        ),
        "interpretation": {
            "claim_boundary": "development robustness evidence only; no clean-confirmation claim",
            "global_gas_action": "not_opened_in_this_test",
            "next_stage": "Proceed to Phase 7 with the frozen Phase-5 system unless a separately preregistered Phase-6 successor is justified by this result.",
        },
    }
    text = json.dumps(result, indent=2) + "\n"
    RESULT.write_text(text, encoding="utf-8", newline="\n")
    CANONICAL.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({
        "baseline_standard_net_pnl_usd": baseline["standard_net_pnl_usd"],
        "annual_standard_net_pnl_usd": annual["standard_net_pnl_usd"],
        "annual_refit_advances": advance,
        "decision_gates": gates,
        "result": str(RESULT.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
