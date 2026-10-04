from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path.cwd().resolve()
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts" / "research")]

import run_issue465_block1_controller_v3 as runner

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    precompute_comparable_refs,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    build_rich_expert_consequences,
    precompute_rich_surfaces_incremental,
    rich_effectiveness_surface_for_day,
)


def timed(name, fn):
    start = time.perf_counter()
    value = fn()
    print(f"{name}: {time.perf_counter() - start:.3f}s", flush=True)
    return value

prereg = runner.load_prereg()
state, v2_runner, v1_runner, v1_prereg = timed("load_state", lambda: runner.load_state(prereg))
path = timed(
    "execution_path",
    lambda: runner.build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg),
)
specialists, _ = timed(
    "specialists", lambda: v2_runner.build_controller_specialists(state, v1_runner)
)
execution = prereg["execution_contract"]
base_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
horizons = tuple(int(v) for v in prereg["opportunity_horizons_sessions"])
base = timed(
    "base_consequences",
    lambda: build_base_consequences(
        specialists, path, horizons=horizons,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    ),
)
expert_paths = runner.load_expert_paths()
context, columns = runner.build_controller_context(state, expert_paths, prereg)
refs = timed(
    "comparable_refs",
    lambda: precompute_comparable_refs(context, context_columns=columns, k=10),
)
foundation_actuals = timed(
    "foundation_actuals", lambda: runner.load_foundation_actuals(expert_paths, state)
)
rich = timed(
    "rich_consequences",
    lambda: build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    ),
)
surfaces = timed(
    "incremental_rich_surfaces",
    lambda: precompute_rich_surfaces_incremental(rich, context, refs),
)
indices = [0, int(prereg["block_contract"]["warmup_completed_trading_sessions"]), len(state) - 1]
for index in indices:
    stamp = pd.Timestamp(state.iloc[index]["decision_time"])
    expected = timed(
        f"reference_surface_{index}",
        lambda stamp=stamp: rich_effectiveness_surface_for_day(rich, stamp, refs[stamp]),
    )
    pd.testing.assert_frame_equal(surfaces[stamp], expected, check_exact=True)
    print(f"surface_{index}_exact: PASS rows={len(expected)}", flush=True)
