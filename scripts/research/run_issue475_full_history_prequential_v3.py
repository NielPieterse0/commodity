from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from commodity.v2_adaptive_controller import PROTECTED_START
from commodity.v3_prequential import (
    PrequentialConfig,
    RobustnessConfig,
    attach_foundation_experts,
    build_default_candidate_signals,
    build_one_session_execution_frame,
    default_candidate_specs,
    evaluate_robustness,
    future_invariance_proof,
    run_prequential,
    score_exposure_path,
    select_smallest_passing_architecture,
    validate_authoritative_freeze,
    validate_prequential_frame,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
EXPERIMENT = PROGRAMME / (
    "lines/001-v2-optimization-execution/experiments/475-full-history-adaptive-edge"
)
PREFLIGHT = EXPERIMENT / "preflight.json"
FREEZE = EXPERIMENT / "design-freeze.json"
SEALED_REGISTRY = PROGRAMME / "sealed-windows.json"
LINE = PROGRAMME / "lines/001-v2-optimization-execution/line.json"
EVIDENCE_MAP = PROGRAMME / "evidence-map.json"
INFERENCE_LEDGER = PROGRAMME / "inference-ledger.json"
DECISIONS = PROGRAMME / "decisions.json"
AUTHORITY_PATHS = (LINE, EVIDENCE_MAP, INFERENCE_LEDGER, DECISIONS)
MAIN_REPO = REPO.parents[2] if REPO.parent.name == "worktrees" else REPO
MARKET_INPUTS = MAIN_REPO / (
    ".work/worktrees/356-market-only-nested-walk-forward/.work/checkpoints/"
    "356-market-only-nested-walk-forward/inputs"
)
FEATURES = MARKET_INPUTS / "features.parquet"
SESSIONS = MARKET_INPUTS / "session-path.parquet"
EXPECTED_FEATURE_SHA256 = (
    "b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e"
)
EXPECTED_SESSION_SHA256 = (
    "0fe87ea79a56f98fb9d445e89e3d65b48ae7bb1175e06ba9b97da68ebe6b01e8"
)
FOUNDATION = REPO / ".work/changes/358-foundation-specialists"
TIMESFM = FOUNDATION / "timesfm-features.csv"
KRONOS = FOUNDATION / "kronos-features.csv"
EXPECTED_TIMESFM_SHA256 = (
    "692930439b863208b47dbeff246fd9790b4f2239f5434e72448538bc674aedc6"
)
EXPECTED_KRONOS_SHA256 = (
    "98010ff7329c312cf04dbd4902d3fa6b3fe71ea562054c897eaf338e3f94df6c"
)
SEALED_WINDOW_ID = "programme004-databento-2023-plus-protected-v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        frame.to_json(
            orient="records",
            lines=True,
            date_format="iso",
            double_precision=15,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _sealed_window(registry: dict[str, Any]) -> dict[str, Any]:
    matches = [
        item
        for item in registry.get("windows", [])
        if item.get("sealed_window_id") == SEALED_WINDOW_ID
    ]
    if len(matches) != 1:
        raise RuntimeError("issue475 protected 2023+ sealed window is missing or ambiguous")
    window = matches[0]
    if window.get("openings") != []:
        raise RuntimeError("issue475 protected confirmation already has an opening")
    if window.get("eligibility") != "ineligible":
        raise RuntimeError("issue475 protected window must remain ineligible during research")
    if window.get("start") != "2023-01-01T00:00:00Z":
        raise RuntimeError("issue475 protected window start changed")
    return window


def _source_identity() -> dict[str, str]:
    required = (FEATURES, SESSIONS, TIMESFM, KRONOS)
    if any(not path.is_file() for path in required):
        raise RuntimeError("issue475 frozen pre-2023 source set is incomplete")
    feature_sha = sha256_file(FEATURES)
    session_sha = sha256_file(SESSIONS)
    timesfm_sha = sha256_file(TIMESFM)
    kronos_sha = sha256_file(KRONOS)
    expected = {
        "features_sha256": (feature_sha, EXPECTED_FEATURE_SHA256),
        "session_path_sha256": (session_sha, EXPECTED_SESSION_SHA256),
        "timesfm_features_sha256": (timesfm_sha, EXPECTED_TIMESFM_SHA256),
        "kronos_features_sha256": (kronos_sha, EXPECTED_KRONOS_SHA256),
    }
    for key, (observed, wanted) in expected.items():
        if observed != wanted:
            raise RuntimeError(f"issue475 frozen source identity changed: {key}")
    return {
        "features_sha256": feature_sha,
        "session_path_sha256": session_sha,
        "timesfm_features_sha256": timesfm_sha,
        "kronos_features_sha256": kronos_sha,
        "sealed_registry_sha256": sha256_file(SEALED_REGISTRY),
    }


def current_identity() -> dict[str, str]:
    identity = _source_identity()
    identity.update(
        {
            "engine_sha256": sha256_file(REPO / "src/commodity/v3_prequential.py"),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
        }
    )
    return identity


def authority_identity() -> dict[str, str]:
    missing = [str(path.relative_to(REPO)) for path in AUTHORITY_PATHS if not path.is_file()]
    if missing:
        raise RuntimeError(f"issue475 programme authority files missing: {missing}")
    return {
        path.relative_to(REPO).as_posix(): sha256_file(path)
        for path in AUTHORITY_PATHS
    }


def load_safe_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    _source_identity()
    features = pd.read_parquet(FEATURES)
    sessions = pd.read_parquet(SESSIONS)
    features["trade_date"] = pd.to_datetime(features["trade_date"], utc=True)
    features["available_at"] = pd.to_datetime(features["available_at"], utc=True)
    for column in ("trade_date", "session_open", "available_at", "next_session_open"):
        sessions[column] = pd.to_datetime(sessions[column], utc=True)
    if (features["available_at"] >= PROTECTED_START).any():
        raise RuntimeError("issue475 feature source crosses protected 2023+ boundary")
    if (sessions["next_session_open"] >= PROTECTED_START).any():
        raise RuntimeError("issue475 session outcomes cross protected 2023+ boundary")
    return features, sessions


def build_full_history_frame() -> pd.DataFrame:
    features, sessions = load_safe_inputs()
    frame = build_one_session_execution_frame(features, sessions)
    timesfm = pd.read_csv(TIMESFM)
    kronos = pd.read_csv(KRONOS)
    frame = attach_foundation_experts(frame, timesfm, kronos)
    signals = build_default_candidate_signals(frame)
    signal_columns = [column for column in signals if column.startswith("signal_")]
    for column in signal_columns:
        frame[column] = signals[column].to_numpy(dtype=float)
    return validate_prequential_frame(frame, default_candidate_specs())


def preflight() -> dict[str, Any]:
    registry = json.loads(SEALED_REGISTRY.read_text(encoding="utf-8"))
    window = _sealed_window(registry)
    frame = build_full_history_frame()
    config = PrequentialConfig()
    checks = {
        "row_count_exceeds_initial_training": len(frame) > config.initial_train_rows,
        "decision_times_unique": bool(frame["decision_time"].is_unique),
        "all_decisions_pre2023": bool((frame["decision_time"] < PROTECTED_START).all()),
        "all_outcomes_pre2023": bool((frame["outcome_available_at"] < PROTECTED_START).all()),
        "strict_future_outcomes": bool(
            (frame["decision_time"] < frame["outcome_available_at"]).all()
        ),
        "protected_window_registered": window["sealed_window_id"] == SEALED_WINDOW_ID,
        "protected_window_unopened": window["openings"] == [],
    }
    report = {
        "schema_version": 1,
        "issue": 475,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "eligible_rows": len(frame),
        "first_decision_time": frame["decision_time"].min(),
        "last_decision_time": frame["decision_time"].max(),
        "last_outcome_available_at": frame["outcome_available_at"].max(),
        "checks": checks,
        "identity": current_identity(),
    }
    report["preflight_sha256"] = stable_sha(report)
    _write_json(PREFLIGHT, report)
    if report["status"] != "PASS":
        raise RuntimeError("issue475 preflight failed")
    return report


def freeze_design() -> dict[str, Any]:
    if not PREFLIGHT.is_file():
        raise RuntimeError("issue475 design freeze requires passing preflight")
    preflight_report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if preflight_report.get("status") != "PASS":
        raise RuntimeError("issue475 design freeze requires PASS preflight")
    identity = current_identity()
    if preflight_report.get("identity") != identity:
        raise RuntimeError("issue475 preflight identity is stale")
    config = PrequentialConfig()
    robustness = RobustnessConfig()
    freeze = {
        "schema_version": 1,
        "issue": 475,
        "status": "FROZEN_BEFORE_AUTHORITATIVE_TRAVERSAL",
        "protected_confirmation_accessed": False,
        "protected_start": PROTECTED_START.isoformat(),
        "identity": identity,
        "authority_identity": authority_identity(),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "prequential_config": asdict(config),
        "robustness_config": asdict(robustness),
        "candidate_specs": [asdict(spec) for spec in default_candidate_specs()],
        "benchmark_contract": [
            "flat",
            "always_short",
            "trend_short",
            "curve_short",
            "trend_curve_short",
            "current_v3",
            "negative_control_inverted_trend",
        ],
        "selection_rule": "smallest architecture passing all frozen robustness gates",
        "role_dispositions": {
            "timesfm": "challenger_only_prior_phase4_direct_promotion_failed",
            "kronos": "challenger_only_prior_short_side_evidence_negative",
            "volatility_jump": "risk_veto_challengers_not_assumed_directional_edges",
            "fundamentals": "held_no_complete_bound_full_history_PIT_source_in_issue475_runner",
            "seasonality": "retained_as_available_context_but_no_standalone_directional_rule_without_predeclared_mechanism",
            "long": "TimesFM long lane is a challenger and receives no symmetric default privilege",
            "current_v3": "legacy directional reference only; not represented as an exact full-history replay of the Block-1-only 96-candidate meta-controller",
        },
        "no_rescue_rules": [
            "No feature, threshold, candidate, cadence, memory, execution assumption, or risk gate may change during the authoritative chronological traversal.",
            "No protected 2023+ file may be decoded, scored, visualized, summarized, or used for redesign.",
            "A profitable candidate receives no credit unless it improves on its declared simpler parent under severe execution and recurrence gates.",
            "Failed specialists remain registered and may decay to zero weight rather than being manually deleted mid-run.",
        ],
        "search_budget": {
            "candidate_count": len(default_candidate_specs()),
            "bounded_tree_only": True,
            "manual_midrun_changes": 0,
        },
    }
    _write_json(FREEZE, freeze)
    return freeze


def _require_committed_clean_freeze() -> dict[str, Any]:
    if _git_text("status", "--porcelain"):
        raise RuntimeError("issue475 authoritative traversal requires a clean committed worktree")
    relative = FREEZE.relative_to(REPO).as_posix()
    committed = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{relative}"],
        capture_output=True,
        check=False,
    )
    if committed.returncode != 0:
        raise RuntimeError("issue475 design freeze is not committed at HEAD")
    if committed.stdout != FREEZE.read_bytes():
        raise RuntimeError("issue475 local design freeze differs from committed HEAD")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    validate_authoritative_freeze(freeze, current_identity())
    if freeze.get("preflight_sha256") != sha256_file(PREFLIGHT):
        raise RuntimeError("issue475 preflight changed after design freeze")
    if freeze.get("authority_identity") != authority_identity():
        raise RuntimeError("issue475 programme authority changed after design freeze")
    return freeze


def _summary(consequences: pd.DataFrame) -> dict[str, Any]:
    frame = consequences.copy()
    returns = pd.to_numeric(frame["realized_net_return"], errors="raise").astype(float)
    signal = pd.to_numeric(frame["signal"], errors="raise").astype(float)
    equity = 1.0 + returns.cumsum()
    peak = equity.cummax().clip(lower=1e-12)
    drawdown = (peak - equity) / peak
    years = pd.to_datetime(frame["decision_time"], utc=True).dt.year
    yearly = returns.groupby(years).sum()
    return {
        "total_net_return": float(returns.sum()),
        "max_drawdown_fraction": float(drawdown.max()) if len(drawdown) else 0.0,
        "active_rows": int(signal.ne(0.0).sum()),
        "positive_years": int((yearly > 0.0).sum()),
        "year_count": len(yearly),
        "yearly_net_return": {str(key): float(value) for key, value in yearly.items()},
    }


def score_authoritative() -> dict[str, Any]:
    freeze = _require_committed_clean_freeze()
    frame = build_full_history_frame()
    config = PrequentialConfig()
    robustness_config = RobustnessConfig()
    specs = default_candidate_specs()
    result = run_prequential(frame, specs, config)
    robustness = evaluate_robustness(
        result.candidate_consequences,
        specs,
        robustness_config,
    )
    selected = select_smallest_passing_architecture(robustness, specs)
    adaptive = score_exposure_path(
        frame,
        result.decisions["target_exposure"],
        config,
    )
    invariance = future_invariance_proof(
        frame,
        specs,
        config,
        cut_indices=(len(frame) // 3, 2 * len(frame) // 3),
        mutation_scale=-37.0,
    )
    if invariance["status"] != "PASS":
        raise RuntimeError("issue475 full future-invariance proof failed")
    decision_path = EXPERIMENT / "decision-ledger.jsonl"
    learning_path = EXPERIMENT / "learning-ledger.jsonl"
    evidence_path = EXPERIMENT / "specialist-lifetime-evidence.jsonl"
    candidate_path = EXPERIMENT / "candidate-consequences.jsonl"
    adaptive_path = EXPERIMENT / "adaptive-consequences.jsonl"
    edge_path = EXPERIMENT / "edge-contribution.json"
    robustness_path = EXPERIMENT / "robustness.json"
    invariance_path = EXPERIMENT / "future-invariance.json"
    _write_jsonl(decision_path, result.decisions)
    _write_jsonl(learning_path, result.learning_events)
    _write_jsonl(evidence_path, result.evidence)
    _write_jsonl(candidate_path, result.candidate_consequences)
    _write_jsonl(adaptive_path, adaptive)
    _write_json(edge_path, result.edge_contribution.to_dict(orient="records"))
    _write_json(robustness_path, robustness.to_dict(orient="records"))
    _write_json(invariance_path, invariance)

    adaptive_summary = {
        scenario: _summary(adaptive.loc[adaptive["scenario"] == scenario])
        for scenario in ("base", "severe")
    }
    benchmark_totals = (
        result.candidate_consequences.groupby(["candidate_id", "scenario"])[
            "realized_net_return"
        ]
        .sum()
        .unstack(fill_value=0.0)
        .reset_index()
        .to_dict(orient="records")
    )
    payload = {
        "schema_version": 1,
        "issue": 475,
        "status": "AUTHORITATIVE_PRE2023_TRAVERSAL_COMPLETE",
        "protected_confirmation_accessed": False,
        "protected_start": PROTECTED_START.isoformat(),
        "design_freeze_sha256": sha256_file(FREEZE),
        "design_freeze_identity": freeze["identity"],
        "source_identity": current_identity(),
        "decision_row_count": len(result.decisions),
        "learning_event_count": len(result.learning_events),
        "evidence_row_count": len(result.evidence),
        "candidate_consequence_row_count": len(result.candidate_consequences),
        "adaptive_freeze_sha256": result.freeze_sha256,
        "selected_smallest_passing_architecture": selected,
        "adaptive_performance": adaptive_summary,
        "benchmark_totals": benchmark_totals,
        "robustness": robustness.to_dict(orient="records"),
        "edge_contribution": result.edge_contribution.to_dict(orient="records"),
        "future_invariance": invariance,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "head_sha": _git_text("rev-parse", "HEAD"),
        },
    }
    artifact_paths = (
        decision_path,
        learning_path,
        evidence_path,
        candidate_path,
        adaptive_path,
        edge_path,
        robustness_path,
        invariance_path,
    )
    payload["artifacts"] = {
        path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in artifact_paths
    }
    payload["result_sha256"] = stable_sha(payload)
    result_path = EXPERIMENT / "research-result.json"
    _write_json(result_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"preflight", "freeze", "score"}:
        raise SystemExit(
            "usage: run_issue475_full_history_prequential_v3.py {preflight|freeze|score}"
        )
    if args[0] == "preflight":
        payload = preflight()
    elif args[0] == "freeze":
        payload = freeze_design()
    else:
        payload = score_authoritative()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
