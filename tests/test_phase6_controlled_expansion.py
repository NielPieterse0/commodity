from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "run_phase6_controlled_expansion.py"


def _module():
    spec = importlib.util.spec_from_file_location("phase6_controlled_expansion", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase6_reproduces_frozen_comparator_and_keeps_2023_sealed() -> None:
    module = _module()
    scores = pd.read_csv(module.SCORES)
    scores["year"] = scores["year"].astype(int)
    assert scores["year"].max() == 2022
    baseline = module.summarize(module.build_path(scores, "two_year"))
    annual = module.summarize(module.build_path(scores, "annual"))
    advances, gates = module.decide(baseline, annual)

    assert baseline["standard_net_pnl_usd"] == 13980.0
    assert annual["standard_net_pnl_usd"] == 17160.0
    assert [row["year"] for row in annual["yearly_path"]] == list(range(2017, 2023))
    assert gates == {
        "net_pnl_noninferior": True,
        "median_noninferior": True,
        "worst_year_noninferior": True,
        "cost_bounded": True,
        "drawdown_noninferior": False,
    }
    assert advances is False
