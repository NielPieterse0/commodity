from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

import run_issue428_decision_optimization as issue428
import run_issue459_joint_advantage as issue459

from commodity import v2_decision_optimization as dec
from commodity import v2_joint_advantage as joint
from commodity.market_only_phase2 import _load_inherited_risk_and_costs

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue429-prereg-v1.json"
PREFLIGHT = PROGRAMME / "issue429-preflight-v1.json"
LEDGER = PROGRAMME / "issue429-trials-v1.jsonl"
RESULT = PROGRAMME / "issue429-result-v1.json"
ISSUE459_WAVE2_PREREG = PROGRAMME / "issue459-wave2-prereg-v2.json"
ISSUE459_WAVE2_PREFLIGHT = PROGRAMME / "issue459-wave2-preflight-v2.json"
ISSUE459_WAVE2_RESULT = PROGRAMME / "issue459-wave2-result-v2.json"
ISSUE459_WAVE2_LEDGER = PROGRAMME / "issue459-wave2-trials-v2.jsonl"
PHASE2 = REPO / "config/phase2_market_only.json"
EXPECTED_PREREG_SHA256 = "0ec059451809fc65d2e8543cb51235c3abd151d0ae483eeaa2503341191bb73e"
PROTECTED_START = pd.Timestamp("2023-01-01", tz="UTC")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def load_prereg() -> dict[str, Any]:
    if sha256_file(PREREG) != EXPECTED_PREREG_SHA256:
        raise RuntimeError("issue429 frozen preregistration identity changed")
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_issue429_scoring":
        raise RuntimeError("issue429 preregistration is not frozen")
    boundary = payload.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue429 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue429 protected evidence flag is not false")
    return payload


def context_columns_for_ablation(
    selected_representations: Mapping[str, str],
    excluded_retained_families: Sequence[str],
) -> list[str]:
    selected_families = (
        "market_structure.positioning",
        "ta.range_breakout",
        "ta.trend_strength",
        "ta.volume_confirmation",
    )
    fixed_families = {
        "volatility_tail.jump_intensity": "feature_issue427_jump_intensity",
        "volatility_tail.vol_of_vol": "feature_issue427_vol_of_vol",
    }
    excluded = {str(value) for value in excluded_retained_families}
    known = {*selected_families, *fixed_families}
    unknown = sorted(excluded - known)
    if unknown:
        raise RuntimeError(f"issue429 unknown retained context families: {unknown}")
    missing = sorted(set(selected_families) - set(selected_representations))
    if missing:
        raise RuntimeError(f"issue429 missing selected context representations: {missing}")
    columns = [
        str(selected_representations[family])
        for family in selected_families
        if family not in excluded
    ]
    columns.extend(
        column for family, column in fixed_families.items() if family not in excluded
    )
    if len(columns) != len(set(columns)):
        raise RuntimeError("issue429 decision context contains duplicate columns")
    return columns


def _validated_policy(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "fill_trade_date",
        "signal_timestamp",
        "fill_timestamp",
        "target_end_timestamp",
        "signal_requested_position",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"issue429 policy missing columns: {missing}")
    out = frame.copy().sort_values("fill_timestamp", kind="stable").reset_index(drop=True)
    for column in ("fill_trade_date", "signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        out[column] = pd.to_datetime(out[column], utc=True, errors="raise")
    if (
        (out["fill_trade_date"] >= PROTECTED_START).any()
        or (out["signal_timestamp"] >= PROTECTED_START).any()
        or (out["fill_timestamp"] >= PROTECTED_START).any()
        or (out["target_end_timestamp"] >= PROTECTED_START).any()
    ):
        raise RuntimeError("issue429 protected 2023+ evidence is forbidden")
    if (out["signal_timestamp"] >= out["fill_timestamp"]).any():
        raise RuntimeError("issue429 signal timestamp must be before fill")
    positions = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    if not positions.isin([-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0]).all():
        raise RuntimeError("issue429 requested position is outside inherited bounds")
    out["signal_requested_position"] = positions
    return out

def _validated_sessions(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "session_open"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"issue429 session path missing columns: {missing}")
    out = frame[["trade_date", "session_open"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="raise")
    out["session_open"] = pd.to_datetime(out["session_open"], utc=True, errors="raise")
    out = out.sort_values("trade_date", kind="stable").reset_index(drop=True)
    if out["trade_date"].duplicated().any():
        raise RuntimeError("issue429 session path has duplicate trade dates")
    return out


def _one_per_target_window(frame: pd.DataFrame) -> pd.DataFrame:
    keep: list[bool] = []
    active_end: pd.Timestamp | None = None
    for row in frame.itertuples(index=False):
        fill = pd.Timestamp(row.fill_timestamp)
        allowed = active_end is None or fill >= active_end
        keep.append(allowed)
        if allowed and float(row.signal_requested_position) != 0.0:
            active_end = pd.Timestamp(row.target_end_timestamp)
    return frame.loc[keep].reset_index(drop=True)


def _ignore_same_direction(frame: pd.DataFrame) -> pd.DataFrame:
    keep: list[bool] = []
    active_position = 0.0
    active_end: pd.Timestamp | None = None
    for row in frame.itertuples(index=False):
        fill = pd.Timestamp(row.fill_timestamp)
        if active_end is not None and fill >= active_end:
            active_position = 0.0
            active_end = None
        position = float(row.signal_requested_position)
        duplicate_refresh = active_position != 0.0 and position == active_position
        keep.append(not duplicate_refresh)
        if duplicate_refresh:
            continue
        if position == 0.0:
            active_position = 0.0
            active_end = None
        else:
            active_position = position
            active_end = pd.Timestamp(row.target_end_timestamp)
    return frame.loc[keep].reset_index(drop=True)


def _exit_only_on_opposite(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    active_position = 0.0
    active_end: pd.Timestamp | None = None
    for index, row in out.iterrows():
        fill = pd.Timestamp(row["fill_timestamp"])
        if active_end is not None and fill >= active_end:
            active_position = 0.0
            active_end = None
        position = float(row["signal_requested_position"])
        opposite = active_position * position < 0.0
        if opposite:
            out.at[index, "signal_requested_position"] = 0.0
            active_position = 0.0
            active_end = None
        elif position == 0.0:
            active_position = 0.0
            active_end = None
        else:
            active_position = position
            active_end = pd.Timestamp(row["target_end_timestamp"])
    return out

def _delay_decisions(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
    delay_sessions: int,
) -> pd.DataFrame:
    if delay_sessions < 0:
        raise RuntimeError("issue429 decision delay must be nonnegative")
    if delay_sessions == 0:
        return frame
    session_lookup = {value: index for index, value in enumerate(sessions["trade_date"])}
    rows: list[pd.Series] = []
    for _, row in frame.iterrows():
        trade_date = pd.Timestamp(row["fill_trade_date"])
        if trade_date not in session_lookup:
            raise RuntimeError("issue429 decision date is absent from session path")
        delayed_index = session_lookup[trade_date] + delay_sessions
        if delayed_index >= len(sessions):
            continue
        revised = row.copy()
        revised["fill_trade_date"] = sessions.loc[delayed_index, "trade_date"]
        revised["fill_timestamp"] = sessions.loc[delayed_index, "session_open"]
        if pd.Timestamp(revised["fill_timestamp"]) >= pd.Timestamp(revised["target_end_timestamp"]):
            continue
        rows.append(revised)
    return pd.DataFrame(rows, columns=frame.columns).reset_index(drop=True)

def _cap_holds(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
    max_hold_sessions: int,
) -> pd.DataFrame:
    if max_hold_sessions < 1:
        raise RuntimeError("issue429 maximum hold must be positive")
    session_lookup = {value: index for index, value in enumerate(sessions["trade_date"])}
    out = frame.copy()
    for index, row in out.iterrows():
        trade_date = pd.Timestamp(row["fill_trade_date"])
        if trade_date not in session_lookup:
            raise RuntimeError("issue429 hold decision date is absent from session path")
        end_index = session_lookup[trade_date] + max_hold_sessions
        if end_index >= len(sessions):
            continue
        cap = pd.Timestamp(sessions.loc[end_index, "session_open"])
        if cap < pd.Timestamp(row["target_end_timestamp"]):
            out.at[index, "target_end_timestamp"] = cap
    return out

def transform_policy_decisions(
    policy: pd.DataFrame,
    session_path: pd.DataFrame,
    variant: Mapping[str, object],
) -> pd.DataFrame:
    out = _validated_policy(policy)
    sessions = _validated_sessions(session_path)
    if str(variant.get("abstain_mode", "flat")) == "hold":
        out = out.loc[out["signal_requested_position"].ne(0.0)].reset_index(drop=True)
    if str(variant.get("cadence_mode", "all")) == "one_per_target_window":
        out = _one_per_target_window(out)
    if str(variant.get("same_direction_mode", "refresh")) == "ignore_while_active":
        out = _ignore_same_direction(out)
    if str(variant.get("opposite_mode", "reverse")) == "exit_only":
        out = _exit_only_on_opposite(out)
    delay = int(variant.get("decision_delay_sessions", 0))
    out = _delay_decisions(out, sessions, delay)
    hold = variant.get("max_hold_sessions")
    if hold is not None:
        out = _cap_holds(out, sessions, int(hold))
    if len(out):
        if out["fill_trade_date"].duplicated().any():
            raise RuntimeError("issue429 transform created duplicate decision dates")
        if (out["fill_timestamp"] >= out["target_end_timestamp"]).any():
            raise RuntimeError("issue429 transform created nonpositive holding interval")
    out["issue429_variant_id"] = str(variant.get("id", "unnamed"))
    return out.sort_values("fill_timestamp", kind="stable").reset_index(drop=True)


def _parent_wave2_config(
    prereg: Mapping[str, Any],
) -> tuple[object, dict[str, Any]]:
    wave2 = issue459.load_wave2_prereg()
    policy_id = str(prereg["parent"]["policy_id"])
    matches = [config for config in joint.build_wave2_configs(wave2) if config.config_id == policy_id]
    if len(matches) != 1:
        raise RuntimeError(f"issue429 parent policy identity changed: {policy_id}")
    config = matches[0]
    parent = prereg["parent"]
    if str(config.short_mode) != str(parent["timesfm_short_mode"]):
        raise RuntimeError("issue429 parent TimesFM mode changed")
    if str(config.long_mode) != str(parent["kronos_long_mode"]):
        raise RuntimeError("issue429 parent Kronos mode changed")
    return config, wave2


def _parent_result_row(prereg: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = json.loads(ISSUE459_WAVE2_RESULT.read_text(encoding="utf-8"))
    parent = prereg["parent"]
    if result.get("result_sha256") != parent["issue459_wave2_result_identity"]:
        raise RuntimeError("issue429 parent result identity changed")
    rows = [
        dict(row)
        for row in result.get("passing_policies", [])
        if str(row.get("policy_id")) == str(parent["policy_id"])
    ]
    if len(rows) != 1:
        raise RuntimeError("issue429 promoted parent is absent from #459 passing policies")
    observed = float(rows[0]["mean_outer_monthly_net_return_delta"])
    expected = float(parent["mean_outer_monthly_net_return_delta"])
    if abs(observed - expected) > 1e-12:
        raise RuntimeError("issue429 parent development economics changed")
    return result, rows[0]


def preflight(*, write: bool = True) -> dict[str, object]:
    prereg = load_prereg()
    issue428_prereg, features, sessions, _families, _support = issue428._load_inputs()
    parent_config, wave2 = _parent_wave2_config(prereg)
    parent_result, parent_row = _parent_result_row(prereg)
    failures: list[str] = []

    parent = prereg["parent"]
    expected_files = (
        (ISSUE459_WAVE2_PREREG, parent["issue459_wave2_prereg_sha256"], "wave2_prereg"),
        (ISSUE459_WAVE2_RESULT, parent["issue459_wave2_result_file_sha256"], "wave2_result"),
        (ISSUE459_WAVE2_LEDGER, parent["issue459_wave2_trial_ledger_sha256"], "wave2_ledger"),
    )
    for path, expected, label in expected_files:
        observed = sha256_file(path)
        if observed != str(expected):
            failures.append(f"parent_{label}_identity_changed:{observed}")

    parent_preflight = json.loads(ISSUE459_WAVE2_PREFLIGHT.read_text(encoding="utf-8"))
    if parent_preflight.get("status") != "PASS":
        failures.append("parent_wave2_preflight_not_pass")
    if parent_preflight.get("protected_confirmation_accessed") is not False:
        failures.append("parent_wave2_preflight_protected_access_changed")
    if parent_result.get("preflight_sha256") != parent_preflight.get("preflight_sha256"):
        failures.append("parent_wave2_preflight_binding_changed")

    expected_trial_count = (
        len(prereg["contribution_ablation"]["policies"])
        + len(prereg["lifecycle_search"]["variants"])
    ) * len(prereg["evaluation"]["outer_blocks"]) * len(prereg["evaluation"]["cost_profiles"])
    declared_trial_count = int(prereg["evaluation"]["expected_outer_cost_trial_count"])
    if expected_trial_count != declared_trial_count:
        failures.append(f"trial_budget_changed:{expected_trial_count}!={declared_trial_count}")

    enriched = issue428._features_with_volatility_tail(features)
    selected_reps = issue428._selected_representations()
    for outer_id in map(str, prereg["evaluation"]["outer_blocks"]):
        selected = selected_reps.get(outer_id, {})
        for policy in prereg["contribution_ablation"]["policies"]:
            excluded = policy.get("excluded_retained_families", [])
            if not excluded:
                continue
            columns = context_columns_for_ablation(selected, list(map(str, excluded)))
            missing = sorted(set(columns) - set(enriched.columns))
            if missing:
                failures.append(f"missing_context_columns:{outer_id}:{policy['id']}:{missing}")

    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    fixed = prereg["fixed_safety"]
    if abs(float(risk.peak_drawdown_kill_fraction) - float(fixed["peak_drawdown_kill_fraction"])) > 1e-12:
        failures.append("peak_drawdown_safety_changed")
    if abs(float(risk.daily_loss_fraction) - float(fixed["daily_loss_fraction"])) > 1e-12:
        failures.append("daily_loss_safety_changed")
    missing_costs = sorted(set(map(str, prereg["evaluation"]["cost_profiles"])) - set(cost_profiles))
    if missing_costs:
        failures.append(f"missing_cost_profiles:{missing_costs}")

    specialist_rows: dict[str, int] = {}
    specialist_frames: dict[str, pd.DataFrame] = {}
    for name, value_column in (("timesfm", "timesfm_point_return"), ("kronos", "kronos_close_return")):
        spec = wave2["specialist_inputs"][name]
        path = REPO / str(spec["path"])
        if sha256_file(path) != str(spec["sha256"]):
            failures.append(f"{name}_feature_identity_changed")
            continue
        frame = issue459._load_specialist_frame(path, value_column)
        specialist_frames[name] = frame
        specialist_rows[name] = len(frame)
        if len(frame) != len(features):
            failures.append(f"{name}_row_count_changed:{len(frame)}!={len(features)}")

    parent_construction: dict[str, object] = {}
    if not failures and {"timesfm", "kronos"} <= set(specialist_frames):
        selected_models = issue428._selected_model_configs()
        matched_controls = issue459.v2.load_issue426_outer_matched_controls(issue428.ISSUE425)
        wave1_configs = joint.build_wave1_configs(issue459.load_prereg())
        parent_wave1 = issue459._wave1_config_for_policy(
            wave1_configs,
            parent_config.parent_policy_id,
            "base",
        )
        for outer_id in map(str, prereg["evaluation"]["outer_blocks"]):
            block, promoted, contribution, lifecycle = _build_outer_policy_sets(
                outer_id=outer_id,
                prereg=prereg,
                issue428_prereg=issue428_prereg,
                features=enriched,
                sessions=sessions,
                cfg=cfg,
                selected_reps=selected_reps,
                selected_models=selected_models,
                matched_controls=matched_controls,
                parent_wave1=parent_wave1,
                parent_wave2=parent_config,
                timesfm=specialist_frames["timesfm"],
                kronos=specialist_frames["kronos"],
                round_trip_usd=float(cost_profiles["base"].round_trip_usd),
            )
            if len(contribution) != int(prereg["evaluation"]["declared_ablation_policy_count"]):
                failures.append(f"ablation_construction_count_changed:{outer_id}:{len(contribution)}")
            if len(lifecycle) != int(prereg["evaluation"]["declared_lifecycle_variant_count"]):
                failures.append(f"lifecycle_construction_count_changed:{outer_id}:{len(lifecycle)}")
            validated = _validated_policy(promoted)
            parent_construction[outer_id] = {
                "start": block["start"],
                "end": block["end"],
                "decision_rows": len(validated),
                "requested_nonzero_rows": int(validated["signal_requested_position"].ne(0.0).sum()),
                "max_fill_trade_date": str(validated["fill_trade_date"].max()),
                "max_target_end_timestamp": str(validated["target_end_timestamp"].max()),
            }

    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 429,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "feature_rows": len(features),
        "session_rows": len(sessions),
        "expected_outer_cost_trial_count": declared_trial_count,
        "parent_policy_id": str(parent["policy_id"]),
        "parent_short_mode": str(parent_config.short_mode),
        "parent_long_mode": str(parent_config.long_mode),
        "parent_mean_outer_monthly_net_return_delta": float(parent_row["mean_outer_monthly_net_return_delta"]),
        "parent_construction": parent_construction,
        "timesfm_rows": specialist_rows.get("timesfm", 0),
        "kronos_rows": specialist_rows.get("kronos", 0),
        "failures": failures,
        "prereg_sha256": sha256_file(PREREG),
        "issue448_preflight_sha256": sha256_file(issue428.issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(issue428.issue448.CACHE / "preflight-features.parquet"),
        "issue448_family_cache_sha256": sha256_file(issue428.issue448.CACHE / "preflight-families.json"),
        "issue459_wave2_preflight_sha256": sha256_file(ISSUE459_WAVE2_PREFLIGHT),
        "issue459_wave2_result_sha256": sha256_file(ISSUE459_WAVE2_RESULT),
        "issue459_wave2_ledger_sha256": sha256_file(ISSUE459_WAVE2_LEDGER),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    report["preflight_sha256"] = stable_sha(report)
    if write:
        PREFLIGHT.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return report


def evaluate_lifecycle_trials(
    trials: pd.DataFrame,
    prereg: Mapping[str, Any],
) -> list[dict[str, object]]:
    required = {
        "stage",
        "policy_id",
        "outer_id",
        "cost_profile",
        "mean_monthly_net_return_delta",
        "selected_trades",
        "nonempty_months",
        "kill_trigger_regression",
        "largest_incremental_month_fraction",
        "max_drawdown_fraction",
    }
    missing = sorted(required - set(trials.columns))
    if missing:
        raise RuntimeError(f"issue429 lifecycle trial summary missing columns: {missing}")
    frame = trials.loc[trials["stage"].astype(str).eq("lifecycle_variant")].copy()
    outers = [str(value) for value in prereg["evaluation"]["outer_blocks"]]
    costs = [str(value) for value in prereg["evaluation"]["cost_profiles"]]
    expected_pairs = {(outer, cost) for outer in outers for cost in costs}
    controls = prereg["effective_sample_controls"]
    gate = prereg["promotion_gate"]
    rows: list[dict[str, object]] = []
    for policy_id, group in frame.groupby("policy_id", sort=True):
        observed_pairs = {
            (str(row.outer_id), str(row.cost_profile))
            for row in group.itertuples(index=False)
        }
        if observed_pairs != expected_pairs or len(group) != len(expected_pairs):
            continue
        base = group.loc[group["cost_profile"].astype(str).eq("base")].copy()
        higher = group.loc[~group["cost_profile"].astype(str).eq("base")].copy()
        base_delta = pd.to_numeric(base["mean_monthly_net_return_delta"], errors="raise")
        selected = pd.to_numeric(base["selected_trades"], errors="raise")
        months = pd.to_numeric(base["nonempty_months"], errors="raise")
        concentration = pd.to_numeric(
            base["largest_incremental_month_fraction"], errors="raise"
        )
        mean_delta = float(base_delta.mean())
        nonnegative_fraction = float(base_delta.ge(0.0).mean())
        effective_pass = bool(
            selected.ge(int(controls["minimum_risk_executed_trades_per_outer"])).all()
            and months.ge(int(controls["minimum_nonempty_months_per_outer"])).all()
        )
        kill_regression = bool(group["kill_trigger_regression"].astype(bool).any())
        higher_cost_nonnegative = bool(
            pd.to_numeric(higher["mean_monthly_net_return_delta"], errors="raise")
            .ge(0.0)
            .all()
        )
        concentration_pass = bool(concentration.le(0.5).all())
        passes = bool(
            mean_delta > float(gate["mean_outer_monthly_net_return_improvement_gt"])
            and nonnegative_fraction >= float(gate["nonnegative_outer_fraction_gte"])
            and effective_pass
            and not kill_regression
            and higher_cost_nonnegative
            and concentration_pass
        )
        rows.append(
            {
                "policy_id": str(policy_id),
                "mean_outer_monthly_net_return_delta": mean_delta,
                "nonnegative_outer_fraction": nonnegative_fraction,
                "effective_sample_pass": effective_pass,
                "kill_trigger_regression": kill_regression,
                "higher_cost_nonnegative": higher_cost_nonnegative,
                "concentration_pass": concentration_pass,
                "max_drawdown_fraction": float(
                    pd.to_numeric(base["max_drawdown_fraction"], errors="raise").max()
                ),
                "passes_promotion_gate": passes,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["passes_promotion_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            float(row["max_drawdown_fraction"]),
            str(row["policy_id"]),
        ),
    )


def _require_preflight() -> dict[str, Any]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue429 scoring requires completed no-scoring preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue429 preflight is not a passing no-scoring report")
    if report.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue429 preflight protected-evidence flag changed")
    expected = {
        "prereg_sha256": sha256_file(PREREG),
        "issue448_preflight_sha256": sha256_file(issue428.issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(
            issue428.issue448.CACHE / "preflight-features.parquet"
        ),
        "issue448_family_cache_sha256": sha256_file(
            issue428.issue448.CACHE / "preflight-families.json"
        ),
        "issue459_wave2_preflight_sha256": sha256_file(ISSUE459_WAVE2_PREFLIGHT),
        "issue459_wave2_result_sha256": sha256_file(ISSUE459_WAVE2_RESULT),
        "issue459_wave2_ledger_sha256": sha256_file(ISSUE459_WAVE2_LEDGER),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue429 preflight is stale: {key}")
    return report


def _frozen_parent_trials(prereg: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in ISSUE459_WAVE2_LEDGER.read_text(encoding="utf-8").splitlines()
        if line
    ]
    parent_id = str(prereg["parent"]["policy_id"])
    selected = [row for row in rows if str(row.get("policy_id")) == parent_id]
    expected_pairs = {
        (str(outer), str(cost))
        for outer in prereg["evaluation"]["outer_blocks"]
        for cost in prereg["evaluation"]["cost_profiles"]
    }
    by_pair = {(str(row["outer_id"]), str(row["cost_profile"])): row for row in selected}
    if set(by_pair) != expected_pairs or len(selected) != len(expected_pairs):
        raise RuntimeError("issue429 frozen parent trial accounting changed")
    return by_pair


def _assert_parent_reproduction(
    *,
    score: Mapping[str, object],
    replay_summary: Mapping[str, object],
    effective: Mapping[str, object],
    frozen: Mapping[str, Any],
    outer_id: str,
    cost_profile: str,
) -> None:
    frozen_score = frozen["score"]
    for key in (
        "mean_monthly_net_return",
        "total_net_pnl_usd",
        "transaction_cost_usd",
        "turnover",
        "max_drawdown_fraction",
    ):
        if abs(float(score[key]) - float(frozen_score[key])) > 1e-10:
            raise RuntimeError(f"issue429 parent reproduction changed:{outer_id}:{cost_profile}:{key}")
    for key in ("trade_count", "month_count", "session_count"):
        if int(score[key]) != int(frozen_score[key]):
            raise RuntimeError(f"issue429 parent reproduction changed:{outer_id}:{cost_profile}:{key}")
    if int(effective["selected_trades"]) != int(frozen["selected_trades"]):
        raise RuntimeError(f"issue429 parent executed sample changed:{outer_id}:{cost_profile}")
    if int(effective["nonempty_months"]) != int(frozen["nonempty_months"]):
        raise RuntimeError(f"issue429 parent active months changed:{outer_id}:{cost_profile}")
    if int(replay_summary.get("risk_shutdown_sessions", 0)) != int(
        frozen["replay_summary"].get("risk_shutdown_sessions", 0)
    ):
        raise RuntimeError(f"issue429 parent risk replay changed:{outer_id}:{cost_profile}")


def _decision_gate_policy(
    *,
    history: pd.DataFrame,
    outer: pd.DataFrame,
    signal_columns: Sequence[str],
    issue428_prereg: Mapping[str, Any],
    gate_config_id: str,
    boundary: pd.Timestamp,
) -> pd.DataFrame:
    state, _annotated_history, annotated_outer = issue428._annotated_context(
        history,
        outer,
        signal_columns,
        issue428_prereg,
        outcome_available_before=boundary,
    )
    configs = issue428._config_map(issue428_prereg)
    if gate_config_id not in configs:
        raise RuntimeError(f"issue429 inherited gate is unavailable: {gate_config_id}")
    return issue428._score_policy(
        annotated_outer,
        configs[gate_config_id],
        state,
        {},
        signal_columns,
    )


def _wave1_variant(
    parent: joint.JointWave1Config,
    *,
    lifecycle: str | None = None,
) -> joint.JointWave1Config:
    revised_lifecycle = lifecycle or parent.lifecycle
    return joint.JointWave1Config(
        config_id=f"issue429__{parent.side_scope}__{parent.gate_id}__{revised_lifecycle}",
        side_scope=parent.side_scope,
        gate_id=parent.gate_id,
        position_fraction=parent.position_fraction,
        lifecycle=revised_lifecycle,
        cost_profile="base",
    )


def _specialist_variant(
    parent: joint.JointWave2Config,
    *,
    long_mode: str | None = None,
) -> joint.JointWave2Config:
    revised_long = parent.long_mode if long_mode is None else long_mode
    return joint.JointWave2Config(
        config_id=f"issue429__short_{parent.short_mode}__long_{revised_long}",
        parent_policy_id=parent.parent_policy_id,
        short_mode=parent.short_mode,
        long_mode=revised_long,
    )


def _trial_row(
    *,
    stage: str,
    policy_id: str,
    outer_id: str,
    cost_profile: str,
    score: Mapping[str, object],
    ledger: pd.DataFrame,
    replay_summary: Mapping[str, object],
    effective: Mapping[str, object],
    parent_score: Mapping[str, object],
    parent_ledger: pd.DataFrame,
    parent_summary: Mapping[str, object],
) -> dict[str, object]:
    mean_delta = float(score["mean_monthly_net_return"]) - float(
        parent_score["mean_monthly_net_return"]
    )
    return {
        "issue": 429,
        "evidence_class": "development",
        "status": "complete",
        "stage": stage,
        "policy_id": policy_id,
        "outer_id": outer_id,
        "cost_profile": cost_profile,
        "mean_monthly_net_return_delta": mean_delta,
        "total_net_pnl_usd_delta": float(score["total_net_pnl_usd"])
        - float(parent_score["total_net_pnl_usd"]),
        "transaction_cost_usd_delta": float(score["transaction_cost_usd"])
        - float(parent_score["transaction_cost_usd"]),
        "turnover_delta": float(score["turnover"]) - float(parent_score["turnover"]),
        "selected_trades": int(effective["selected_trades"]),
        "nonempty_months": int(effective["nonempty_months"]),
        "requested_selected_trades": int(effective["requested_selected_trades"]),
        "kill_trigger_regression": int(replay_summary.get("risk_shutdown_sessions", 0))
        > int(parent_summary.get("risk_shutdown_sessions", 0)),
        "largest_incremental_month_fraction": joint.largest_incremental_month_fraction(
            ledger, parent_ledger
        ),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "component_contribution_mean_monthly_return": -mean_delta
        if stage == "contribution_ablation"
        else None,
        "score": dict(score),
        "replay_summary": dict(replay_summary),
        "effective_sample": dict(effective),
    }


def _build_outer_policy_sets(
    *,
    outer_id: str,
    prereg: Mapping[str, Any],
    issue428_prereg: Mapping[str, Any],
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    selected_reps: Mapping[str, Mapping[str, str]],
    selected_models: Mapping[str, Mapping[str, object]],
    matched_controls: Mapping[str, Mapping[str, object]],
    parent_wave1: joint.JointWave1Config,
    parent_wave2: joint.JointWave2Config,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
    round_trip_usd: float,
) -> tuple[dict[str, str], pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    block = issue428._outer_blocks(cfg)[outer_id]
    full_signal_columns = issue428._signal_columns_for_outer(outer_id, selected_reps)
    opportunities = issue428._build_outer_opportunities(
        target_outer_id=outer_id,
        features=features,
        sessions=sessions,
        cfg=cfg,
        selected_config=selected_models[outer_id],
        matched_config=matched_controls[outer_id]["config"],
        signal_columns=full_signal_columns,
        round_trip_usd=round_trip_usd,
    )
    start = pd.Timestamp(str(block["start"]), tz="UTC")
    end = pd.Timestamp(str(block["end"]), tz="UTC")
    history = dec.completed_history_before(opportunities, start)
    fill_dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    outer = opportunities.loc[(fill_dates >= start) & (fill_dates <= end)].copy()
    if history.empty or outer.empty:
        raise RuntimeError(f"issue429 outer opportunity context is empty: {outer_id}")

    strength_gate = _decision_gate_policy(
        history=history,
        outer=outer,
        signal_columns=full_signal_columns,
        issue428_prereg=issue428_prereg,
        gate_config_id="strength-q50",
        boundary=start,
    )
    wave1_parent = joint.apply_joint_candidate(strength_gate, parent_wave1)
    joined_parent = issue459._join_wave2_specialists(wave1_parent, timesfm, kronos)
    promoted_parent = joint.apply_wave2_specialists(joined_parent, parent_wave2)

    contribution: dict[str, pd.DataFrame] = {"full_promoted_control": promoted_parent}
    for spec in prereg["contribution_ablation"]["policies"]:
        policy_id = str(spec["id"])
        if policy_id == "full_promoted_control":
            continue
        if "long_specialist_mode" in spec:
            contribution[policy_id] = joint.apply_wave2_specialists(
                joined_parent,
                _specialist_variant(parent_wave2, long_mode=str(spec["long_specialist_mode"])),
            )
            continue
        if "gate_id" in spec:
            gate_id = "baseline" if str(spec["gate_id"]) == "baseline" else str(spec["gate_id"])
            baseline_gate = _decision_gate_policy(
                history=history,
                outer=outer,
                signal_columns=full_signal_columns,
                issue428_prereg=issue428_prereg,
                gate_config_id=gate_id,
                boundary=start,
            )
            wave1 = joint.apply_joint_candidate(baseline_gate, parent_wave1)
            joined = issue459._join_wave2_specialists(wave1, timesfm, kronos)
            contribution[policy_id] = joint.apply_wave2_specialists(joined, parent_wave2)
            continue
        if "lifecycle" in spec:
            wave1 = joint.apply_joint_candidate(
                strength_gate,
                _wave1_variant(parent_wave1, lifecycle=str(spec["lifecycle"])),
            )
            joined = issue459._join_wave2_specialists(wave1, timesfm, kronos)
            contribution[policy_id] = joint.apply_wave2_specialists(joined, parent_wave2)
            continue
        excluded = [str(value) for value in spec.get("excluded_retained_families", [])]
        if excluded:
            ablated_columns = context_columns_for_ablation(selected_reps[outer_id], excluded)
            ablated_gate = _decision_gate_policy(
                history=history,
                outer=outer,
                signal_columns=ablated_columns,
                issue428_prereg=issue428_prereg,
                gate_config_id="strength-q50",
                boundary=start,
            )
            wave1 = joint.apply_joint_candidate(ablated_gate, parent_wave1)
            joined = issue459._join_wave2_specialists(wave1, timesfm, kronos)
            contribution[policy_id] = joint.apply_wave2_specialists(joined, parent_wave2)
            continue
        raise RuntimeError(f"issue429 unsupported ablation specification: {policy_id}")

    lifecycle: dict[str, pd.DataFrame] = {}
    for variant in prereg["lifecycle_search"]["variants"]:
        transformed = transform_policy_decisions(promoted_parent, sessions, variant)
        transformed_dates = pd.to_datetime(
            transformed["fill_trade_date"], utc=True, errors="raise"
        )
        lifecycle[str(variant["id"])] = transformed.loc[
            (transformed_dates >= start) & (transformed_dates <= end)
        ].reset_index(drop=True)
    return dict(block), promoted_parent, contribution, lifecycle


def _contribution_summary(trials: pd.DataFrame) -> list[dict[str, object]]:
    frame = trials.loc[
        trials["stage"].astype(str).eq("contribution_ablation")
        & trials["cost_profile"].astype(str).eq("base")
    ].copy()
    rows: list[dict[str, object]] = []
    for policy_id, group in frame.groupby("policy_id", sort=True):
        deltas = pd.to_numeric(group["mean_monthly_net_return_delta"], errors="raise")
        rows.append(
            {
                "policy_id": str(policy_id),
                "mean_outer_monthly_net_return_delta_vs_parent": float(deltas.mean()),
                "mean_component_contribution_to_parent": float(-deltas.mean()),
                "outer_deltas": {
                    str(row.outer_id): float(row.mean_monthly_net_return_delta)
                    for row in group.itertuples(index=False)
                },
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -float(row["mean_component_contribution_to_parent"]),
            str(row["policy_id"]),
        ),
    )


def score_issue429() -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg = load_prereg()
    issue428_prereg, features, sessions, _families, _support = issue428._load_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    features = issue428._features_with_volatility_tail(features)
    selected_reps = issue428._selected_representations()
    selected_models = issue428._selected_model_configs()
    matched_controls = issue459.v2.load_issue426_outer_matched_controls(issue428.ISSUE425)

    parent_wave2, wave2 = _parent_wave2_config(prereg)
    wave1_configs = joint.build_wave1_configs(issue459.load_prereg())
    parent_wave1 = issue459._wave1_config_for_policy(
        wave1_configs,
        parent_wave2.parent_policy_id,
        "base",
    )
    timesfm = issue459._load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["timesfm"]["path"]),
        "timesfm_point_return",
    )
    kronos = issue459._load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["kronos"]["path"]),
        "kronos_close_return",
    )
    frozen_parent = _frozen_parent_trials(prereg)
    trials: list[dict[str, object]] = []
    parent_diagnostics: dict[str, object] = {}

    for outer_id in map(str, prereg["evaluation"]["outer_blocks"]):
        print(f"issue429 scoring outer={outer_id} build_context", flush=True)
        block, promoted_parent, contribution, lifecycle = _build_outer_policy_sets(
            outer_id=outer_id,
            prereg=prereg,
            issue428_prereg=issue428_prereg,
            features=features,
            sessions=sessions,
            cfg=cfg,
            selected_reps=selected_reps,
            selected_models=selected_models,
            matched_controls=matched_controls,
            parent_wave1=parent_wave1,
            parent_wave2=parent_wave2,
            timesfm=timesfm,
            kronos=kronos,
            round_trip_usd=float(cost_profiles["base"].round_trip_usd),
        )
        parent_replays: dict[
            str, tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any]]
        ] = {}
        for cost_name in map(str, prereg["evaluation"]["cost_profiles"]):
            replay = issue459._score_policy(
                sessions,
                promoted_parent,
                start=str(block["start"]),
                end=str(block["end"]),
                risk=risk,
                costs=cost_profiles[cost_name],
                multiplier=multiplier,
            )
            _assert_parent_reproduction(
                score=replay[0],
                replay_summary=replay[2],
                effective=replay[3],
                frozen=frozen_parent[(outer_id, cost_name)],
                outer_id=outer_id,
                cost_profile=cost_name,
            )
            parent_replays[cost_name] = replay
        parent_diagnostics[outer_id] = {
            "reproduced": True,
            "scores": {name: replay[0] for name, replay in parent_replays.items()},
        }
        print(f"issue429 scoring outer={outer_id} parent_reproduction=PASS", flush=True)

        stage_policies = (
            ("contribution_ablation", contribution),
            ("lifecycle_variant", lifecycle),
        )
        for stage, policies in stage_policies:
            for policy_id, policy in policies.items():
                for cost_name in map(str, prereg["evaluation"]["cost_profiles"]):
                    parent_score, parent_ledger, parent_summary, _parent_effective = (
                        parent_replays[cost_name]
                    )
                    if stage == "contribution_ablation" and policy_id == "full_promoted_control":
                        score, ledger, replay_summary, effective = parent_replays[cost_name]
                    else:
                        score, ledger, replay_summary, effective = issue459._score_policy(
                            sessions,
                            policy,
                            start=str(block["start"]),
                            end=str(block["end"]),
                            risk=risk,
                            costs=cost_profiles[cost_name],
                            multiplier=multiplier,
                        )
                    trials.append(
                        _trial_row(
                            stage=stage,
                            policy_id=str(policy_id),
                            outer_id=outer_id,
                            cost_profile=cost_name,
                            score=score,
                            ledger=ledger,
                            replay_summary=replay_summary,
                            effective=effective,
                            parent_score=parent_score,
                            parent_ledger=parent_ledger,
                            parent_summary=parent_summary,
                        )
                    )
                print(
                    f"issue429 scoring outer={outer_id} stage={stage} policy={policy_id} complete",
                    flush=True,
                )

    expected_trials = int(prereg["evaluation"]["expected_outer_cost_trial_count"])
    if len(trials) != expected_trials:
        raise RuntimeError(f"issue429 trial accounting changed:{len(trials)}!={expected_trials}")
    trial_frame = pd.DataFrame(trials)
    lifecycle_evaluation = evaluate_lifecycle_trials(trial_frame, prereg)
    passing = [row for row in lifecycle_evaluation if row["passes_promotion_gate"]]
    contribution = _contribution_summary(trial_frame)
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 429,
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "claim_boundary": prereg["claim_boundary"],
        "parent_policy_id": prereg["parent"]["policy_id"],
        "parent_reproduction": parent_diagnostics,
        "declared_contribution_policy_count": int(
            prereg["evaluation"]["declared_ablation_policy_count"]
        ),
        "declared_lifecycle_variant_count": int(
            prereg["evaluation"]["declared_lifecycle_variant_count"]
        ),
        "trial_count": len(trials),
        "contribution_summary": contribution,
        "lifecycle_evaluation": lifecycle_evaluation,
        "passing_lifecycle_variants": passing,
        "passing_lifecycle_variant_count": len(passing),
        "event_time_lane": dict(prereg["event_time_lane"]),
        "disposition": (
            "FREEZE_ISSUE429_DEVELOPMENT_CANDIDATE"
            if passing
            else "NO_ISSUE429_LIFECYCLE_IMPROVEMENT"
        ),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "prereg_sha256": sha256_file(PREREG),
        "issue459_wave2_result_identity": prereg["parent"]["issue459_wave2_result_identity"],
        "issue459_wave2_trial_ledger_sha256": sha256_file(ISSUE459_WAVE2_LEDGER),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    result["trial_ledger_file_sha256"] = sha256_file(LEDGER)
    result["result_sha256"] = stable_sha(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result
