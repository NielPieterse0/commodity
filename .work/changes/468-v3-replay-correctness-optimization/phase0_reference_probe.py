from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path.cwd().resolve()
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts" / "research"))

import run_issue465_block1_controller_v3 as runner

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    precompute_comparable_refs,
)
from commodity.v2_adaptive_controller_v3 import replay_candidate, run_meta_controller
from commodity.v2_adaptive_controller_v3_diagnostics import (
    build_rich_expert_consequences,
    causal_oracle_weight_predictor,
    causal_primitive_oracle_winner_predictor,
    foundation_horizon_signals,
    hindsight_attribute_weight_oracle,
    precompute_rich_surfaces_incremental,
)

stages: dict[str, float] = {}


def timed(name: str, fn):
    started = time.perf_counter()
    value = fn()
    stages[name] = time.perf_counter() - started
    print(f"{name}: {stages[name]:.3f}s", flush=True)
    return value

prereg = runner.load_prereg()
state, v2_runner, v1_runner, v1_prereg = timed(
    "load_state", lambda: runner.load_state(prereg)
)
path = timed(
    "execution_path",
    lambda: runner.build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg),
)
specialists, weighted_attributes = timed(
    "specialists", lambda: v2_runner.build_controller_specialists(state, v1_runner)
)
families = v2_runner.controller_family_map(v1_prereg, weighted_attributes)
configs = runner.structural_grid(prereg)[:1]
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
)
expert_paths = timed("expert_paths", runner.load_expert_paths)
context_state, context_columns = timed(
    "controller_context",
    lambda: runner.build_controller_context(state, expert_paths, prereg),
)
refs = timed(
    "comparable_refs",
    lambda: precompute_comparable_refs(
        context_state, context_columns=context_columns, k=10
    ),
)
assert len(refs) == len(state)
horizon_signals = timed(
    "foundation_horizon_signals",
    lambda: foundation_horizon_signals(expert_paths, horizons),
)
foundation_actuals = timed(
    "foundation_actuals",
    lambda: runner.load_foundation_actuals(expert_paths, state),
)
rich_base = timed(
    "rich_consequences",
    lambda: build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    ),
)
surfaces = timed(
    "rich_surfaces_incremental",
    lambda: precompute_rich_surfaces_incremental(rich_base, context_state, refs),
)
warmup = int(prereg["block_contract"]["warmup_completed_trading_sessions"])
primitive_oracle = timed(
    "primitive_oracle",
    lambda: runner.oracle_first_diagnostic(rich_base, state["decision_time"].tolist()),
)
primitive_predictor = timed(
    "primitive_predictor",
    lambda: causal_primitive_oracle_winner_predictor(
        state, primitive_oracle["winner_by_day"], weighted_attributes,
        k=int(prereg["primitive_oracle_winner_predictor"]["predictor_neighbors"]),
    ),
)
attribute_oracle = timed(
    "attribute_oracle",
    lambda: hindsight_attribute_weight_oracle(
        state, weighted_attributes, path,
        sparse_k=int(prereg["attribute_weight_oracle"]["sparse_k"]),
        sparse_ks=tuple(int(value) for value in prereg["attribute_weight_oracle"]["sparse_ks"]),
        horizons=tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        max_abs_contracts=float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        exposure_step_contracts=float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        round_trip_cost_usd=2.0 * base_cost,
    ),
)
weight_predictor = timed(
    "oracle_weight_predictor",
    lambda: causal_oracle_weight_predictor(
        state, attribute_oracle, weighted_attributes,
        k=int(prereg["attribute_weight_oracle"]["predictor_neighbors"]),
        sparse_k=int(prereg["attribute_weight_oracle"]["sparse_k"]),
        horizons=tuple(int(value) for value in prereg["attribute_weight_oracle"]["horizons_sessions"]),
        max_abs_contracts=float(prereg["attribute_weight_oracle"]["max_abs_contracts"]),
        exposure_step_contracts=float(prereg["attribute_weight_oracle"]["exposure_step_contracts"]),
    ),
)
scenario_replays = {}
for scenario in prereg["execution_sensitivity"]["scenarios"]:
    scenario_id = str(scenario["id"])
    scenario_replays[scenario_id] = [timed(
        f"candidate_replay_{scenario_id}",
        lambda scenario=scenario: replay_candidate(
            configs[0], state, specialists, path, surfaces, refs, families,
            execution_scenario=scenario,
            horizon_signals_by_time=horizon_signals,
            max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
            initial_capital=float(execution["starting_capital_usd"]),
            multiplier=float(execution["contract_multiplier_mmbtu"]),
            base_cost_per_side=base_cost,
            initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
            max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
            max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
            max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
        ),
    )]

brain, consequences, freeze_sha = timed(
    "meta_controller",
    lambda: run_meta_controller(
        scenario_replays["base"],
        {key: value for key, value in scenario_replays.items() if key != "base"},
        state, path, specialists=specialists, surfaces=surfaces, refs_by_time=refs,
        objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ensemble_size=int(prereg["meta_controller"]["ensemble_size"]),
        structural_cadence=int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        stress_floor=float(prereg["meta_controller"]["stress_floor_30_session_net_return"]),
        max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
        initial_capital=float(execution["starting_capital_usd"]),
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        cost_per_side=base_cost,
        initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
        max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
        max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
        max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
    ),
)
proof = timed(
    "complete_future_invariance",
    lambda: runner.full_future_invariance_proof(
        scenario_replays, brain, state, path, specialists, surfaces, rich_base,
        expert_paths, foundation_actuals, refs, families, configs, prereg,
        v2_runner, v1_runner,
    ),
)
output = {
    "status": proof["status"],
    "source_identity": runner.current_code_identity(),
    "environment_identity": runner.runtime_environment_identity(),
    "candidate_count": len(configs),
    "scenario_count": len(scenario_replays),
    "decision_count": len(state),
    "freeze_sha256": freeze_sha,
    "stages_seconds": stages,
    "total_seconds": sum(stages.values()),
    "proof": proof,
}
output_path = (
    REPO / ".work" / "changes" / "468-v3-replay-correctness-optimization"
    / "phase0-corrected-optimized-probe.json"
)
output_path.write_text(json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps({
    "status": output["status"],
    "total_seconds": output["total_seconds"],
    "output": str(output_path),
}, indent=2), flush=True)
if proof["status"] != "PASS":
    raise SystemExit(2)
