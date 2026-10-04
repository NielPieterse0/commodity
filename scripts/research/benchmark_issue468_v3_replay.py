from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts" / "research")]

import run_issue465_block1_controller_v3 as runner

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    precompute_comparable_refs,
)
from commodity.v2_adaptive_controller_v3 import (
    build_meta_score_tensor,
    precompute_profile_score_cache,
    replay_candidate,
    replay_candidate_scenarios,
    run_meta_controller,
)
from commodity.v2_adaptive_controller_v3_diagnostics import (
    build_rich_expert_consequences,
    foundation_horizon_signals,
    precompute_rich_surfaces_incremental,
)


def timed(name: str, fn, metrics: dict[str, float]):
    started = time.perf_counter()
    value = fn()
    metrics[name] = time.perf_counter() - started
    print(f"{name}: {metrics[name]:.3f}s", flush=True)
    return value


def replay_kwargs(prereg: dict, execution: dict, base_cost: float) -> dict:
    sizing = prereg["dynamic_sizing"]
    return {
        "max_abs_contracts": float(sizing["max_abs_contracts"]),
        "initial_capital": float(execution["starting_capital_usd"]),
        "multiplier": float(execution["contract_multiplier_mmbtu"]),
        "base_cost_per_side": float(base_cost),
        "initial_margin_usd_per_contract": float(
            execution["initial_margin_usd_per_contract"]
        ),
        "max_margin_fraction": float(sizing["max_margin_fraction"]),
        "max_notional_leverage": float(sizing["max_notional_leverage"]),
        "max_drawdown_fraction": float(sizing["max_drawdown_fraction"]),
    }


def main() -> int:
    metrics: dict[str, float] = {}
    prereg = runner.load_prereg()
    state, v2_runner, v1_runner, v1_prereg = timed(
        "load_state", lambda: runner.load_state(prereg), metrics
    )
    path = timed(
        "execution_path",
        lambda: runner.build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg),
        metrics,
    )
    specialists, weighted_attributes = timed(
        "specialists", lambda: v2_runner.build_controller_specialists(state, v1_runner), metrics
    )
    families = v2_runner.controller_family_map(v1_prereg, weighted_attributes)
    config = runner.structural_grid(prereg)[0]
    execution = prereg["execution_contract"]
    base_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
    horizons = tuple(int(value) for value in prereg["opportunity_horizons_sessions"])
    base = timed(
        "base_consequences",
        lambda: build_base_consequences(
            specialists, path, horizons=horizons,
            multiplier=float(execution["contract_multiplier_mmbtu"]),
            capital_usd=float(execution["starting_capital_usd"]),
            cost_per_side_usd=base_cost,
        ),
        metrics,
    )
    expert_paths = runner.load_expert_paths()
    context, context_columns = runner.build_controller_context(state, expert_paths, prereg)
    refs = timed(
        "comparable_refs",
        lambda: precompute_comparable_refs(context, context_columns=context_columns, k=10),
        metrics,
    )
    horizon_signals = foundation_horizon_signals(expert_paths, horizons)
    foundation_actuals = timed(
        "foundation_actuals", lambda: runner.load_foundation_actuals(expert_paths, state), metrics
    )
    rich = timed(
        "rich_consequences",
        lambda: build_rich_expert_consequences(
            base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
            multiplier=float(execution["contract_multiplier_mmbtu"]),
            capital_usd=float(execution["starting_capital_usd"]),
            cost_per_side_usd=base_cost,
        ),
        metrics,
    )
    surfaces = timed(
        "rich_surfaces_incremental",
        lambda: precompute_rich_surfaces_incremental(rich, context, refs),
        metrics,
    )
    profile_cache = timed(
        "profile_score_cache_one_candidate",
        lambda: precompute_profile_score_cache(surfaces, [config]),
        metrics,
    )
    scenarios = tuple(prereg["execution_sensitivity"]["scenarios"])
    kwargs = replay_kwargs(prereg, execution, base_cost)

    legacy: dict[str, object] = {}
    started = time.perf_counter()
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        legacy[scenario_id] = replay_candidate(
            config, state, specialists, path, surfaces, refs, families,
            execution_scenario=scenario,
            horizon_signals_by_time=horizon_signals,
            profile_score_cache=profile_cache,
            **kwargs,
        )
    metrics["candidate_three_scenarios_legacy"] = time.perf_counter() - started
    print(
        f"candidate_three_scenarios_legacy: "
        f"{metrics['candidate_three_scenarios_legacy']:.3f}s",
        flush=True,
    )
    batch = timed(
        "candidate_three_scenarios_batch",
        lambda: replay_candidate_scenarios(
            config, state, specialists, path, surfaces, refs, families,
            execution_scenarios=scenarios,
            horizon_signals_by_time=horizon_signals,
            profile_score_cache=profile_cache,
            **kwargs,
        ),
        metrics,
    )
    for scenario_id, expected in legacy.items():
        actual = batch[scenario_id]
        pd.testing.assert_frame_equal(actual.decisions, expected.decisions, check_exact=True)
        pd.testing.assert_frame_equal(actual.consequences, expected.consequences, check_exact=True)
        assert actual.summary == expected.summary
    base_replays = [batch["base"]]
    stress_replays = {
        scenario_id: [replay]
        for scenario_id, replay in batch.items()
        if scenario_id != "base"
    }
    tensor = timed(
        "meta_score_tensor_one_candidate",
        lambda: build_meta_score_tensor(
            base_replays, stress_replays, state["decision_time"],
            window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ),
        metrics,
    )
    assert tensor.candidate_ids == (config.config_id,)
    timed(
        "meta_controller_one_candidate",
        lambda: run_meta_controller(
            base_replays, stress_replays, state, path,
            specialists=specialists, surfaces=surfaces, refs_by_time=refs,
            objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
            ensemble_size=1,
            structural_cadence=int(
                prereg["meta_controller"]["structural_ensemble_cadence_sessions"]
            ),
            stress_floor=float(prereg["meta_controller"]["stress_floor_30_session_net_return"]),
            embed_effectiveness_surface=False,
            **{key: value for key, value in kwargs.items() if key != "base_cost_per_side"},
            cost_per_side=base_cost,
        ),
        metrics,
    )
    legacy_seconds = metrics["candidate_three_scenarios_legacy"]
    batch_seconds = metrics["candidate_three_scenarios_batch"]
    result = {
        "schema_version": 1,
        "issue": 468,
        "candidate_config_id": config.config_id,
        "decision_count": len(state),
        "scenario_count": len(scenarios),
        "exact_batch_equivalence": True,
        "candidate_batch_speedup": legacy_seconds / max(batch_seconds, 1e-12),
        "metrics_seconds": metrics,
    }
    output = REPO / ".work" / "changes" / "468-v3-replay-correctness-optimization" / "replay-benchmark.json"
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
