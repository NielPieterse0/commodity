from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts" / "research")]

import run_issue465_block1_controller_v3 as r

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    precompute_comparable_refs,
)
from commodity.v2_adaptive_controller_v3 import run_meta_controller, structural_grid
from commodity.v2_adaptive_controller_v3_diagnostics import (
    build_rich_expert_consequences,
    precompute_rich_surfaces_incremental,
)


def mark(name: str, started: float) -> float:
    now = time.perf_counter()
    print(f"{name}: {now - started:.3f}s", flush=True)
    return now


def main() -> int:
    total_start = last = time.perf_counter()
    prereg = r.load_prereg()
    state, v2_runner, v1_runner, v1_prereg = r.load_state(prereg)
    last = mark("load_state", last)
    path = r.build_execution_path(state, prereg, v2_runner, v1_runner, v1_prereg)
    last = mark("execution_path", last)
    specialists, weighted = v2_runner.build_controller_specialists(state, v1_runner)
    families = v2_runner.controller_family_map(v1_prereg, weighted)
    configs = structural_grid(prereg)
    execution = prereg["execution_contract"]
    base_cost = float(prereg["execution_sensitivity"]["base_cost_usd_per_contract_side"])
    horizons = tuple(int(v) for v in prereg["opportunity_horizons_sessions"])
    base = build_base_consequences(
        specialists, path, horizons=horizons,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
    last = mark("base_consequences", last)
    expert_paths = r.load_expert_paths()
    context_state, context_columns = r.build_controller_context(state, expert_paths, prereg)
    refs = precompute_comparable_refs(context_state, context_columns=context_columns, k=10)
    foundation_actuals = r.load_foundation_actuals(expert_paths, state)
    rich_base = build_rich_expert_consequences(
        base, path, expert_paths=expert_paths, foundation_actuals=foundation_actuals,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=base_cost,
    )
    surfaces = precompute_rich_surfaces_incremental(rich_base, context_state, refs)
    last = mark("rich_surfaces_ready", last)

    checkpoint_root = r.CHECKPOINT_ROOT / "066cfa5de7a648dfbe4130ed"
    progress = json.loads((checkpoint_root / "progress.json").read_text(encoding="utf-8"))
    prior_identity = str(progress["scoring_input_identity_sha256"])
    r.scoring_input_identity_sha256 = lambda: prior_identity
    scenarios = tuple(prereg["execution_sensitivity"]["scenarios"])
    scenario_ids = tuple(str(row["id"]) for row in scenarios)
    scenario_replays = {scenario_id: [] for scenario_id in scenario_ids}
    for number, config in enumerate(configs, start=1):
        cached = r._load_candidate_checkpoint(
            checkpoint_root, number, config, scenario_ids
        )
        if cached is None:
            raise RuntimeError(f"missing checkpoint {number}/{len(configs)}")
        for scenario_id in scenario_ids:
            scenario_replays[scenario_id].append(cached[scenario_id])
    last = mark("load_288_checkpoints", last)

    stress_replays = {
        key: value for key, value in scenario_replays.items() if key != "base"
    }
    brain, _consequences, _freeze = run_meta_controller(
        scenario_replays["base"], stress_replays, state, path,
        specialists=specialists, surfaces=surfaces, refs_by_time=refs,
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
        embed_effectiveness_surface=False,
    )
    last = mark("baseline_meta_controller", last)

    proof = r.full_future_invariance_proof(
        scenario_replays, brain, state, path, specialists, surfaces, rich_base,
        expert_paths, foundation_actuals, refs, families, configs, prereg,
        v2_runner, v1_runner,
    )
    proof_seconds = time.perf_counter() - last
    total_seconds = time.perf_counter() - total_start
    output = ROOT / ".work" / "changes" / "468-v3-replay-correctness-optimization" / "full-invariance-proof.json"
    output.write_text(json.dumps({
        "proof_seconds": proof_seconds,
        "total_seconds": total_seconds,
        "proof": proof,
    }, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"FULL_PROOF_STATUS={proof['status']}", flush=True)
    print(f"FULL_PROOF_SECONDS={proof_seconds:.3f}", flush=True)
    print(f"TOTAL_SECONDS={total_seconds:.3f}", flush=True)
    print(f"STRUCTURAL_PREFIX={proof['all_structural_candidate_decision_prefixes_identical']}", flush=True)
    print(f"META_PREFIX={proof['meta_state_weights_structure_actions_pruning_prefix_identical']}", flush=True)
    print(f"PHASE_PREFIXES={proof['structural_phase_prefixes_identical']}", flush=True)
    print(f"ORACLE_PREFIX={proof['oracle_weight_predictor_prefix_identical']}", flush=True)
    print(f"PRIMITIVE_PREFIX={proof['primitive_oracle_winner_predictor_prefix_identical']}", flush=True)
    return 0 if proof["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
