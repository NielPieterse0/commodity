from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path.cwd().resolve()
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts" / "research")]

import run_issue465_block1_controller_v3 as runner
from benchmark_issue468_v3_replay import replay_kwargs

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    precompute_comparable_refs,
)
from commodity.v2_adaptive_controller_v3 import (
    precompute_profile_score_cache,
    replay_candidate_scenarios,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    build_rich_expert_consequences,
    foundation_horizon_signals,
    precompute_rich_surfaces_incremental,
)


def timed(name, fn):
    started = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - started
    print(f"{name}: {elapsed:.3f}s", flush=True)
    return value, elapsed


prereg = runner.load_prereg()
(state, v2_runner, v1_runner, v1_prereg), load_seconds = timed(
    "load_state", lambda: runner.load_state(prereg)
)
path, path_seconds = timed(
    "execution_path", lambda: runner.build_execution_path(
        state, prereg, v2_runner, v1_runner, v1_prereg
    )
)
(specialists, weighted_attributes), specialist_seconds = timed(
    "specialists", lambda: v2_runner.build_controller_specialists(state, v1_runner)
)
families = v2_runner.controller_family_map(v1_prereg, weighted_attributes)
configs = runner.structural_grid(prereg)
execution = prereg["execution_contract"]
base_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
horizons = tuple(int(value) for value in prereg["opportunity_horizons_sessions"])
base, base_seconds = timed(
    "base_consequences", lambda: build_base_consequences(
        specialists, path, horizons=horizons,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
)
expert_paths = runner.load_expert_paths()
context, context_columns = runner.build_controller_context(state, expert_paths, prereg)
refs, refs_seconds = timed(
    "comparable_refs", lambda: precompute_comparable_refs(
        context, context_columns=context_columns, k=10
    )
)
foundation_actuals = runner.load_foundation_actuals(expert_paths, state)
rich, rich_seconds = timed(
    "rich_consequences", lambda: build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
)
surfaces, surface_seconds = timed(
    "rich_surfaces", lambda: precompute_rich_surfaces_incremental(rich, context, refs)
)
profile_cache, cache_seconds = timed(
    "profile_score_cache_all_configs",
    lambda: precompute_profile_score_cache(surfaces, configs),
)
horizon_signals = foundation_horizon_signals(expert_paths, horizons)
scenarios = tuple(prereg["execution_sensitivity"]["scenarios"])
kwargs = replay_kwargs(prereg, execution, base_cost)
per_candidate = []
started = time.perf_counter()
for index, config in enumerate(configs, start=1):
    candidate_started = time.perf_counter()
    replay_candidate_scenarios(
        config, state, specialists, path, surfaces, refs, families,
        execution_scenarios=scenarios, horizon_signals_by_time=horizon_signals,
        profile_score_cache=profile_cache, **kwargs,
    )
    per_candidate.append(time.perf_counter() - candidate_started)
    if index % 8 == 0 or index == len(configs):
        print(f"candidate_progress={index}/{len(configs)}", flush=True)
candidate_seconds = time.perf_counter() - started
result = {
    "schema_version": 1,
    "issue": 468,
    "candidate_count": len(configs),
    "scenario_count": len(scenarios),
    "prep_seconds": (
        load_seconds + path_seconds + specialist_seconds + base_seconds
        + refs_seconds + rich_seconds + surface_seconds + cache_seconds
    ),
    "profile_score_cache_all_configs_seconds": cache_seconds,
    "candidate_all_seconds": candidate_seconds,
    "candidate_mean_seconds": statistics.mean(per_candidate),
    "candidate_median_seconds": statistics.median(per_candidate),
    "candidate_max_seconds": max(per_candidate),
}
out = REPO / ".work" / "changes" / "468-v3-replay-correctness-optimization" / "candidate-scaling-benchmark.json"
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, sort_keys=True), flush=True)
