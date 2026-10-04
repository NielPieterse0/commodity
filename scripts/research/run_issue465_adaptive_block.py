from __future__ import annotations

import datetime as dt
import hashlib
import io
import itertools
import json
import sys
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from commodity.cftc import parse_cftc_report_dates
from commodity.v2_adaptive_controller import (
    candidate_consequence_store,
    oracle_diagnostic,
    run_adaptive_block,
    sparse_policy_signal,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue465-prereg-v1.json"
INVENTORY = PROGRAMME / "issue465-inventory-v1.json"
MANIFEST = PROGRAMME / "issue465-block1-manifest-v1.json"
PREFLIGHT = PROGRAMME / "issue465-block1-preflight-v1.json"
CANDIDATES = PROGRAMME / "issue465-block1-candidates-v1.json"
EXPERT_ARCHIVE = PROGRAMME / "issue465-block1-expert-archive-v1.jsonl"
PIT_STATE = PROGRAMME / "issue465-block1-pit-state-v1.jsonl"
CONSEQUENCES = PROGRAMME / "issue465-block1-consequences-v1.jsonl"
LEDGER = PROGRAMME / "issue465-block1-ledger-v1.json"
RESULT = PROGRAMME / "issue465-block1-result-v1.json"

MAIN_REPO = REPO.parents[2] if REPO.parent.name == "worktrees" else REPO
MARKET_INPUTS = MAIN_REPO / ".work/worktrees/356-market-only-nested-walk-forward/.work/checkpoints/356-market-only-nested-walk-forward/inputs"
EXPERT_ROOT = MAIN_REPO / ".work/changes/358-foundation-specialists"
TIMESFM = EXPERT_ROOT / "timesfm-features.csv"
KRONOS = EXPERT_ROOT / "kronos-features.csv"
ADVANTAGE_MAP = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-advantage-map-v1.json"
CFTC_URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2010.zip"
CFTC_MARKET_CODE = "023651"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def load_prereg() -> dict[str, object]:
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_issue465_block1_scoring":
        raise RuntimeError("issue465 block1 preregistration is not frozen")
    if payload.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue465 protected evidence boundary changed")
    return payload


def _policy_id(weights: dict[str, float], horizon: int, side: str, exposure: float) -> str:
    weight_id = "+".join(f"{name}:{weight:g}" for name, weight in sorted(weights.items()))
    exposure_id = f"{exposure:g}".replace(".", "p")
    return f"{weight_id}__h{horizon}__{side}__x{exposure_id}"


def build_policy_specs(prereg: dict[str, object]) -> list[dict[str, object]]:
    search = prereg["policy_search_space"]
    specialists = [str(row["id"]) for row in prereg["specialist_library"]]
    weight_sets = [({name: 1.0}, 1) for name in specialists]
    pair_weights = [float(value) for value in search["pair_specialist_weights"]]
    for pair in prereg["sparse_pair_library"]:
        names = [str(value) for value in pair]
        if len(names) != 2 or any(name not in specialists for name in names):
            raise RuntimeError("issue465 sparse pair library is invalid")
        weight_sets.append((dict(zip(names, pair_weights, strict=True)), 2))
    policies: list[dict[str, object]] = [
        {"id": "flat", "weights": {}, "horizon_sessions": 0,
         "side": "flat", "exposure": 0.0, "complexity": 0}
    ]
    for (weights, complexity), horizon, side, exposure in itertools.product(
        weight_sets,
        search["rebalance_horizon_sessions"],
        search["side_modes"],
        search["research_exposure_contracts"],
    ):
        policies.append({
            "id": _policy_id(weights, int(horizon), str(side), float(exposure)),
            "weights": weights,
            "horizon_sessions": int(horizon),
            "side": str(side),
            "exposure": float(exposure),
            "complexity": int(complexity),
        })
    expected = int(search["expected_policy_count"])
    if len(policies) != expected or len({row["id"] for row in policies}) != expected:
        raise RuntimeError("issue465 policy grid identity changed")
    return policies


def eligible_block_origins(origins: pd.DataFrame, end_exclusive: pd.Timestamp) -> pd.DataFrame:
    frame = origins.copy()
    frame["target_end_timestamp"] = pd.to_datetime(frame["target_end_timestamp"], utc=True)
    return frame.loc[frame["target_end_timestamp"] < end_exclusive].reset_index(drop=True)


def canonicalize_executable_origins(
    origins: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    frame = origins.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    if (frame["signal_timestamp"] >= frame["fill_timestamp"]).any():
        raise RuntimeError("issue465 origin signal must strictly precede executable fill")
    duplicate = frame.loc[frame.duplicated("fill_timestamp", keep=False)]
    for _, group in duplicate.groupby("fill_timestamp", sort=False):
        if group["fill_contract_id"].astype(str).nunique() != 1:
            raise RuntimeError("issue465 duplicate fill origins disagree on held contract")
        if group["target_end_timestamp"].nunique() != 1:
            raise RuntimeError("issue465 duplicate fill origins disagree on target end")
    before = len(frame)
    frame = frame.sort_values(
        ["fill_timestamp", "signal_timestamp", "trade_date"], kind="stable"
    ).drop_duplicates("fill_timestamp", keep="last")
    frame = frame.sort_values("signal_timestamp", kind="stable").reset_index(drop=True)
    return frame, {
        "input_origins": before,
        "output_origins": len(frame),
        "collapsed": before - len(frame),
    }


def _verify_file(path: Path, expected_sha: str, label: str) -> str:
    if not path.exists():
        raise RuntimeError(f"issue465 missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected_sha:
        raise RuntimeError(f"issue465 {label} identity changed: {actual}")
    return actual


def load_market_inputs(prereg: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = prereg["source_identity_contract"]
    feature_path = MARKET_INPUTS / "features.parquet"
    session_path = MARKET_INPUTS / "session-path.parquet"
    _verify_file(feature_path, str(source["frozen_market_feature_sha256"]), "market feature")
    _verify_file(session_path, str(source["frozen_session_path_sha256"]), "session path")
    features = pd.read_parquet(feature_path)
    sessions = pd.read_parquet(session_path)
    cutoff = pd.Timestamp("2022-12-31T23:59:59Z")
    if pd.to_datetime(features["trade_date"], utc=True).max() > cutoff:
        raise RuntimeError("issue465 feature source crosses protected boundary")
    return features, sessions


def structural_block_origins(
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    prereg: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, int]]:
    block = prereg["block_contract"]
    start = pd.Timestamp(str(block["start_inclusive"]))
    end = pd.Timestamp(str(block["end_exclusive"]))
    feature_dates = pd.to_datetime(features["trade_date"], utc=True)
    block_features = features.loc[(feature_dates >= start) & (feature_dates < end)].copy()
    block_features["trade_date"] = pd.to_datetime(block_features["trade_date"], utc=True)
    block_features["available_at"] = pd.to_datetime(block_features["available_at"], utc=True)
    path = sessions.copy()
    for column in ("trade_date", "session_open", "available_at", "next_session_open"):
        path[column] = pd.to_datetime(path[column], utc=True)
    selected = path[["trade_date", "available_at"]].rename(
        columns={"available_at": "selected_available_at"}
    )
    merged = block_features.merge(selected, on="trade_date", how="left", validate="one_to_one")
    merged["signal_timestamp"] = merged[["available_at", "selected_available_at"]].max(axis=1)
    records: list[dict[str, object]] = []
    opens = path["session_open"].tolist()
    for row in merged.sort_values("trade_date").itertuples(index=False):
        signal = pd.Timestamp(row.signal_timestamp)
        fill_index = next((i for i, value in enumerate(opens) if pd.Timestamp(value) > signal), None)
        if fill_index is None:
            continue
        fill = path.iloc[fill_index]
        target_end = pd.Timestamp(fill["next_session_open"])
        records.append({
            "trade_date": pd.Timestamp(row.trade_date),
            "signal_timestamp": signal,
            "fill_timestamp": pd.Timestamp(fill["session_open"]),
            "fill_contract_id": str(fill["contract_id"]),
            "target_end_timestamp": target_end,
        })
    origins = eligible_block_origins(pd.DataFrame(records), end)
    return canonicalize_executable_origins(origins)


def load_expert_frame(
    path: Path,
    expected_sha: str,
    value_columns: list[str],
) -> pd.DataFrame:
    _verify_file(path, expected_sha, path.name)
    frame = pd.read_csv(path)
    required = {"trade_date", "prediction_time", "generated_at", *value_columns}
    missing = required.difference(frame.columns)
    if missing:
        raise RuntimeError(f"issue465 expert file missing columns: {sorted(missing)}")
    for column in ("trade_date", "prediction_time", "generated_at"):
        frame[column] = pd.to_datetime(
            frame[column], utc=True, errors="raise", format="mixed"
        )
    return frame[["trade_date", "prediction_time", "generated_at", *value_columns]].copy()


def _historical_cftc_available_at(report_date: pd.Timestamp) -> tuple[pd.Timestamp, str]:
    day = pd.Timestamp(report_date).date()
    publication_day = day + dt.timedelta(days=7)
    basis = "cftc_report_date_plus_7d_conservative"
    if day == dt.date(2012, 11, 27):
        publication_day = dt.date(2012, 12, 5)
        basis = "cftc_2012_republication_announcement"
    elif dt.date(2013, 10, 1) <= day <= dt.date(2013, 11, 5):
        publication_day = dt.date(2013, 11, 8)
        basis = "cftc_2013_shutdown_conservative_catchup_bound"
    elif dt.date(2018, 12, 24) <= day <= dt.date(2019, 3, 19):
        publication_day = dt.date(2019, 3, 31)
        basis = "cftc_2018_2019_shutdown_conservative_catchup_bound"
    local = dt.datetime.combine(
        publication_day, dt.time(23, 59), tzinfo=ZoneInfo("America/New_York")
    )
    return pd.Timestamp(local).tz_convert("UTC"), basis


def load_cftc_2010(prereg: dict[str, object]) -> tuple[pd.DataFrame, dict[str, object]]:
    response = requests.get(CFTC_URL, timeout=60)
    response.raise_for_status()
    content = response.content
    actual_sha = hashlib.sha256(content).hexdigest()
    expected = str(prereg["source_identity_contract"]["cftc_2010_archive_sha256"])
    if actual_sha != expected:
        raise RuntimeError(f"issue465 CFTC 2010 identity changed: {actual_sha}")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [
            item for item in archive.infolist()
            if not item.is_dir() and Path(item.filename).suffix.lower() in {".txt", ".csv"}
        ]
        if len(members) != 1:
            raise RuntimeError("issue465 CFTC archive member identity is ambiguous")
        with archive.open(members[0]) as handle:
            raw = pd.read_csv(handle, dtype=str, low_memory=False)
    raw.columns = [str(column).strip() for column in raw.columns]
    codes = raw["CFTC_Contract_Market_Code"].astype(str).str.strip().str.zfill(6)
    frame = raw.loc[codes.eq(CFTC_MARKET_CODE)].copy()
    frame = frame.loc[frame["FutOnly_or_Combined"].astype(str).str.strip().eq("FutOnly")]
    report_date = parse_cftc_report_dates(frame)
    availability = [_historical_cftc_available_at(value) for value in report_date]
    numeric_columns = [
        "Open_Interest_All",
        "M_Money_Positions_Long_All", "M_Money_Positions_Short_All",
        "Prod_Merc_Positions_Long_All", "Prod_Merc_Positions_Short_All",
    ]
    numeric = {name: pd.to_numeric(frame[name], errors="raise").astype(float) for name in numeric_columns}
    out = pd.DataFrame({
        "positioning_observation_time": report_date,
        "positioning_available_at": [item[0] for item in availability],
        "positioning_availability_basis": [item[1] for item in availability],
        "positioning_open_interest": numeric["Open_Interest_All"],
        "managed_money_net": numeric["M_Money_Positions_Long_All"] - numeric["M_Money_Positions_Short_All"],
        "producer_merchant_net": numeric["Prod_Merc_Positions_Long_All"] - numeric["Prod_Merc_Positions_Short_All"],
    }).sort_values(["positioning_available_at", "positioning_observation_time"], kind="stable")
    out = out.drop_duplicates("positioning_available_at", keep="last").reset_index(drop=True)
    if (out["positioning_available_at"] <= out["positioning_observation_time"]).any():
        raise RuntimeError("issue465 CFTC availability precedes its observation")
    evidence = {
        "url": CFTC_URL,
        "sha256": actual_sha,
        "accepted_target_rows": len(out),
        "raw_rows": len(raw),
        "source_id": "cftc_disaggregated_futures_only_023651_historical",
    }
    return out, evidence


def _merge_cftc(state: pd.DataFrame, cftc: pd.DataFrame) -> pd.DataFrame:
    left = state.sort_values("decision_time").copy()
    right = cftc.sort_values("positioning_available_at").copy()
    merged = pd.merge_asof(
        left, right,
        left_on="decision_time", right_on="positioning_available_at",
        direction="backward", allow_exact_matches=True,
    )
    if merged["producer_merchant_net"].isna().any():
        raise RuntimeError("issue465 block1 has decision rows without prior CFTC positioning")
    merged["positioning_source_id"] = "cftc_disaggregated_futures_only_023651_historical"
    merged["positioning_age_seconds"] = (
        merged["decision_time"] - merged["positioning_available_at"]
    ).dt.total_seconds()
    merged["positioning_age_sessions"] = merged.groupby(
        "positioning_available_at", sort=False
    ).cumcount()
    merged["positioning_vintage"] = "2010_historical_futures_only_archive"
    merged["positioning_revision"] = "conservative_publication_reconstruction"
    return merged


def materialize_expert_archive(prereg: dict[str, object]) -> pd.DataFrame:
    source = prereg["source_identity_contract"]
    if EXPERT_ARCHIVE.exists():
        archive = pd.read_json(EXPERT_ARCHIVE, lines=True, convert_dates=False)
        for column in (
            "trade_date", "timesfm_prediction_time", "timesfm_generated_at",
            "kronos_prediction_time", "kronos_generated_at",
        ):
            archive[column] = pd.to_datetime(
                archive[column], utc=True, errors="raise", format="mixed"
            )
        if archive["timesfm_source_sha256"].nunique() != 1 or archive["kronos_source_sha256"].nunique() != 1:
            raise RuntimeError("issue465 expert archive provenance is ambiguous")
        if archive["timesfm_source_sha256"].iloc[0] != str(source["timesfm_features_sha256"]):
            raise RuntimeError("issue465 TimesFM archive provenance changed")
        if archive["kronos_source_sha256"].iloc[0] != str(source["kronos_features_sha256"]):
            raise RuntimeError("issue465 Kronos archive provenance changed")
        return archive
    timesfm = load_expert_frame(
        TIMESFM, str(source["timesfm_features_sha256"]),
        ["timesfm_point_return", "timesfm_q10_return", "timesfm_q90_return", "timesfm_interval_width"],
    ).rename(columns={"prediction_time": "timesfm_prediction_time", "generated_at": "timesfm_generated_at"})
    kronos = load_expert_frame(
        KRONOS, str(source["kronos_features_sha256"]),
        ["kronos_close_return", "kronos_range_pct"],
    ).rename(columns={"prediction_time": "kronos_prediction_time", "generated_at": "kronos_generated_at"})
    block = prereg["block_contract"]
    start = pd.Timestamp(str(block["start_inclusive"]))
    end = pd.Timestamp(str(block["end_exclusive"]))
    timesfm = timesfm.loc[(timesfm["trade_date"] >= start) & (timesfm["trade_date"] < end)]
    kronos = kronos.loc[(kronos["trade_date"] >= start) & (kronos["trade_date"] < end)]
    archive = timesfm.merge(kronos, on="trade_date", how="inner", validate="one_to_one")
    archive["timesfm_source_sha256"] = str(source["timesfm_features_sha256"])
    archive["kronos_source_sha256"] = str(source["kronos_features_sha256"])
    archive["migration_authority"] = "issue459-wave2-prereg-v2.json_hash_bound_historical_input"
    _write_jsonl(EXPERT_ARCHIVE, archive)
    return archive


def _merge_experts(state: pd.DataFrame, prereg: dict[str, object]) -> pd.DataFrame:
    archive = materialize_expert_archive(prereg)
    out = state.merge(archive, on="trade_date", how="left", validate="one_to_one")
    for prefix in ("timesfm", "kronos"):
        if out[f"{prefix}_generated_at"].isna().any():
            raise RuntimeError(f"issue465 missing {prefix} block1 expert output")
        if (out[f"{prefix}_generated_at"] > out["decision_time"]).any():
            raise RuntimeError(f"issue465 {prefix} output crosses decision boundary")
        out[f"{prefix}_age_seconds"] = (
            out["decision_time"] - out[f"{prefix}_generated_at"]
        ).dt.total_seconds()
    out["timesfm_source_id"] = "issue465_block1_expert_archive"
    out["kronos_source_id"] = "issue465_block1_expert_archive"
    return out


def build_pit_state(prereg: dict[str, object]) -> tuple[pd.DataFrame, dict[str, object]]:
    features, sessions = load_market_inputs(prereg)
    structural, origin_stats = structural_block_origins(features, sessions, prereg)
    feature_frame = features.copy()
    feature_frame["trade_date"] = pd.to_datetime(feature_frame["trade_date"], utc=True)
    feature_frame["available_at"] = pd.to_datetime(feature_frame["available_at"], utc=True)
    state = structural.merge(feature_frame, on="trade_date", how="left", validate="one_to_one")
    state = state.rename(columns={"available_at": "market_available_at"})
    state["decision_time"] = pd.to_datetime(state["signal_timestamp"], utc=True)
    if (state["market_available_at"] > state["decision_time"]).any():
        raise RuntimeError("issue465 market feature crosses decision boundary")
    state["market_observation_time"] = state["trade_date"]
    state["market_source_id"] = "frozen_issue356_market_features"
    state["market_age_seconds"] = (
        state["decision_time"] - state["market_available_at"]
    ).dt.total_seconds()
    state["market_age_sessions"] = 0
    state = _merge_experts(state, prereg)
    cftc, cftc_evidence = load_cftc_2010(prereg)
    state = _merge_cftc(state, cftc)
    if (state["decision_time"] >= pd.Timestamp("2023-01-01", tz="UTC")).any():
        raise RuntimeError("issue465 PIT state crosses protected boundary")
    state = enrich_derived_state(state)
    source_evidence = {
        "market_feature_sha256": sha256_file(MARKET_INPUTS / "features.parquet"),
        "session_path_sha256": sha256_file(MARKET_INPUTS / "session-path.parquet"),
        "timesfm_historical_source_sha256": str(
            prereg["source_identity_contract"]["timesfm_features_sha256"]
        ),
        "kronos_historical_source_sha256": str(
            prereg["source_identity_contract"]["kronos_features_sha256"]
        ),
        "issue465_expert_archive_sha256": sha256_file(EXPERT_ARCHIVE),
        "cftc": cftc_evidence,
        "raw_structural_origin_count": origin_stats["input_origins"],
        "structural_origin_count": origin_stats["output_origins"],
        "collapsed_duplicate_fill_origins": origin_stats["collapsed"],
    }
    return state.sort_values("decision_time").reset_index(drop=True), source_evidence


def _signed(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    return pd.Series(np.sign(numeric), index=values.index, dtype=float)


def enrich_derived_state(state: pd.DataFrame) -> pd.DataFrame:
    out = state.copy()
    settle = np.exp(pd.to_numeric(out["feature_curve_log_settle_m1"], errors="raise"))
    out["derived_settle_m1"] = settle
    out["derived_prior20_settle_max"] = settle.shift(1).rolling(20, min_periods=20).max()
    out["derived_prior20_settle_min"] = settle.shift(1).rolling(20, min_periods=20).min()
    vol20 = pd.to_numeric(out["feature_vol_20"], errors="raise").astype(float)
    out["derived_prior60_vol20_median"] = vol20.shift(1).rolling(60, min_periods=20).median()
    ret1 = pd.to_numeric(out["feature_ret_1"], errors="raise").astype(float)
    out["derived_jump_intensity"] = ret1.abs() / vol20.clip(lower=1e-12)
    out["derived_prior60_jump_q67"] = (
        out["derived_jump_intensity"].shift(1).rolling(60, min_periods=20).quantile(0.67)
    )
    vol5 = pd.to_numeric(out["feature_vol_5"], errors="raise").astype(float)
    out["derived_vol_of_vol"] = vol5.rolling(20, min_periods=5).std(ddof=0)
    out["derived_prior60_vov_q67"] = (
        out["derived_vol_of_vol"].shift(1).rolling(60, min_periods=20).quantile(0.67)
    )
    return out


def build_specialist_signals(state: pd.DataFrame) -> pd.DataFrame:
    state = enrich_derived_state(state)
    out = pd.DataFrame({"decision_time": pd.to_datetime(state["decision_time"], utc=True)})
    out["trend_ret20"] = _signed(state["feature_ret_20"])
    out["trend_ret5"] = _signed(state["feature_ret_5"])
    out["mean_reversion_ret5"] = -out["trend_ret5"]
    out["ma20_trend"] = _signed(state["feature_ma_gap_20"])
    out["ma5_mean_reversion"] = -_signed(state["feature_ma_gap_5"])
    out["curve_slope_direct"] = _signed(state["feature_curve_slope_m1_m4"])
    out["curve_slope_inverse"] = -out["curve_slope_direct"]
    out["season_sin_direct"] = _signed(state["feature_season_sin"])
    out["season_cos_direct"] = _signed(state["feature_season_cos"])
    out["positioning_producer_direct"] = _signed(state["producer_merchant_net"])
    out["positioning_producer_inverse"] = -out["positioning_producer_direct"]
    out["timesfm_direction"] = _signed(state["timesfm_point_return"])
    out["kronos_direction"] = _signed(state["kronos_close_return"])
    breakout = pd.Series(0.0, index=state.index)
    breakout.loc[state["derived_settle_m1"] > state["derived_prior20_settle_max"]] = 1.0
    breakout.loc[state["derived_settle_m1"] < state["derived_prior20_settle_min"]] = -1.0
    out["range_breakout20"] = breakout
    low_vol = state["feature_vol_20"] <= state["derived_prior60_vol20_median"]
    out["low_vol_trend20"] = out["trend_ret20"].where(low_vol.fillna(False), 0.0)
    high_jump = state["derived_jump_intensity"] >= state["derived_prior60_jump_q67"]
    out["high_jump_mean_reversion"] = out["mean_reversion_ret5"].where(high_jump.fillna(False), 0.0)
    low_vov = state["derived_vol_of_vol"] <= state["derived_prior60_vov_q67"]
    out["vol_of_vol_veto_trend"] = out["trend_ret20"].where(low_vov.fillna(False), 0.0)
    signal_columns = [column for column in out.columns if column != "decision_time"]
    if out[signal_columns].isna().any().any():
        raise RuntimeError("issue465 specialist signals contain missing values")
    if not out[signal_columns].isin([-1.0, 0.0, 1.0]).all().all():
        raise RuntimeError("issue465 specialist signals left the bounded direction set")
    return out


def build_policy_matrix(
    state: pd.DataFrame,
    prereg: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, dict[str, object]], list[dict[str, object]]]:
    specialists = build_specialist_signals(state)
    specs = build_policy_specs(prereg)
    columns: dict[str, object] = {"decision_time": specialists["decision_time"].to_numpy()}
    metadata: dict[str, dict[str, object]] = {}
    specialist_values = specialists.drop(columns="decision_time")
    for spec in specs:
        policy_id = str(spec["id"])
        metadata[policy_id] = dict(spec)
        if policy_id == "flat":
            columns[policy_id] = np.zeros(len(specialists), dtype=float)
            continue
        columns[policy_id] = sparse_policy_signal(
            specialist_values,
            weights=dict(spec["weights"]),
            cadence_sessions=int(spec["horizon_sessions"]),
            side=str(spec["side"]),
            exposure=float(spec["exposure"]),
        ).to_numpy()
    matrix = pd.DataFrame(columns)
    return matrix, metadata, specs


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    path.write_text(
        frame.to_json(
            orient="records", lines=True, date_format="iso", double_precision=15
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_inventory(prereg: dict[str, object]) -> dict[str, object]:
    advantage = json.loads(ADVANTAGE_MAP.read_text(encoding="utf-8"))
    family_dispositions = [
        {"family": "market_curve_technical", "block1": "GO", "role": "state_and_specialists"},
        {"family": "timesfm", "block1": "GO", "role": "timestamped_specialist"},
        {"family": "kronos", "block1": "GO", "role": "timestamped_specialist"},
        {"family": "cftc_positioning", "block1": "GO", "role": "state_and_specialist"},
        {"family": "futures_open_interest", "block1": "HOLD", "reason": "no_valid_referenced_records_2010"},
        {"family": "storage", "block1": "HOLD", "reason": "PIT_support_starts_2015_06_19"},
        {"family": "weather", "block1": "HOLD", "reason": "PIT_support_starts_2015_01_15"},
        {"family": "power", "block1": "HOLD", "reason": "historical_publication_timing_not_promoted"},
        {"family": "storage_consensus_surprise", "block1": "HOLD", "reason": "source_not_proven"},
        {"family": "options_implied", "block1": "HOLD", "reason": "activation_gates_not_proven"},
        {"family": "event_time", "block1": "HOLD", "reason": "historical_release_timing_not_proven"},
        {"family": "lng_physical", "block1": "HOLD", "reason": "no_registered_PIT_block1_source_through_issue431"},
    ]
    authority_files = {}
    for issue in (425, 426, 427, 428, 429, 430, 431):
        path = PROGRAMME / f"issue{issue}-result-v1.json"
        if path.exists():
            authority_files[path.name] = sha256_file(path)
    return {
        "schema_version": 1,
        "issue": 465,
        "scope": "block1_only",
        "prior_evidence_map": {
            "path": str(ADVANTAGE_MAP.relative_to(REPO)),
            "sha256": sha256_file(ADVANTAGE_MAP),
            "raw_evidence_count": int(advantage["raw_evidence_count"]),
            "classification_counts": advantage["classification_counts"],
        },
        "authority_result_sha256": authority_files,
        "family_dispositions": family_dispositions,
        "historical_reentry_rule": prereg["historical_reentry_rule"],
        "protected_confirmation_accessed": False,
        "block1_result_evidence_used": False,
    }


def build_manifest(
    prereg: dict[str, object],
    state: pd.DataFrame,
    source_evidence: dict[str, object],
    policies: list[dict[str, object]],
) -> dict[str, object]:
    block = prereg["block_contract"]
    return {
        "schema_version": 1,
        "issue": 465,
        "block_id": block["block_id"],
        "start_inclusive": block["start_inclusive"],
        "end_exclusive": block["end_exclusive"],
        "eligible_decision_rows": len(state),
        "warmup_completed_trading_sessions": block["warmup_completed_trading_sessions"],
        "first_decision_time": state["decision_time"].min(),
        "last_decision_time": state["decision_time"].max(),
        "policy_count": len(policies),
        "later_blocks_available_to_search": False,
        "source_evidence": source_evidence,
        "prereg_sha256": sha256_file(PREREG),
    }


def pit_archive_frame(state: pd.DataFrame) -> pd.DataFrame:
    excluded = {"target_end_timestamp"}
    columns = [column for column in state.columns if column not in excluded]
    return state[columns].copy()


def preflight(*, write: bool = True) -> dict[str, object]:
    prereg = load_prereg()
    state, source_evidence = build_pit_state(prereg)
    policies = build_policy_specs(prereg)
    matrix, _metadata, _ = build_policy_matrix(state, prereg)
    specialists = build_specialist_signals(state)
    block = prereg["block_contract"]
    end = pd.Timestamp(str(block["end_exclusive"]))
    policy_values = matrix.drop(columns="decision_time")
    max_abs = float(policy_values.abs().max().max())
    expected_rows = int(block["expected_executable_decision_rows"])
    checks = {
        "eligible_rows_eq_prereg": len(state) == expected_rows,
        "unique_decision_times": bool(state["decision_time"].is_unique),
        "unique_fill_timestamps": bool(state["fill_timestamp"].is_unique),
        "strict_signal_before_fill": bool((state["decision_time"] < state["fill_timestamp"]).all()),
        "outcomes_mature_inside_block": bool((state["target_end_timestamp"] < end).all()),
        "market_available_by_decision": bool((state["market_available_at"] <= state["decision_time"]).all()),
        "timesfm_available_by_decision": bool((state["timesfm_generated_at"] <= state["decision_time"]).all()),
        "kronos_available_by_decision": bool((state["kronos_generated_at"] <= state["decision_time"]).all()),
        "positioning_available_by_decision": bool((state["positioning_available_at"] <= state["decision_time"]).all()),
        "specialist_count_eq_17": len(specialists.columns) - 1 == 17,
        "policy_count_eq_prereg": len(policies) == int(prereg["policy_search_space"]["expected_policy_count"]),
        "policy_exposure_within_bound": max_abs <= float(prereg["execution_contract"]["max_abs_contracts_first_block"]),
        "protected_confirmation_not_accessed": True,
    }
    status = "PASS" if all(value is True for value in checks.values()) else "FAIL"
    inventory = build_inventory(prereg)
    manifest = build_manifest(prereg, state, source_evidence, policies)
    candidate_payload = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "prereg_sha256": sha256_file(PREREG),
        "policy_grid_sha256": stable_sha(policies),
        "policy_count": len(policies),
        "policies": policies,
        "scoring_performed": False,
    }
    report = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "status": status,
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "code_identity": current_code_identity(),
        "checks": checks,
        "source_evidence": source_evidence,
        "policy_grid_sha256": candidate_payload["policy_grid_sha256"],
        "expert_archive_sha256": sha256_file(EXPERT_ARCHIVE),
        "pit_state_row_count": len(state),
        "pit_state_excludes_future_outcome_values": True,
    }
    if write:
        _write_json(INVENTORY, inventory)
        _write_json(MANIFEST, manifest)
        _write_json(CANDIDATES, candidate_payload)
        _write_jsonl(PIT_STATE, pit_archive_frame(state))
        report["artifact_sha256"] = {
            INVENTORY.name: sha256_file(INVENTORY),
            MANIFEST.name: sha256_file(MANIFEST),
            CANDIDATES.name: sha256_file(CANDIDATES),
            EXPERT_ARCHIVE.name: sha256_file(EXPERT_ARCHIVE),
            PIT_STATE.name: sha256_file(PIT_STATE),
        }
        _write_json(PREFLIGHT, report)
    return report


def performance_summary(
    consequences: pd.DataFrame,
    *,
    starting_capital: float,
    cost_per_side: float,
    margin_per_contract: float,
) -> dict[str, object]:
    frame = consequences.copy()
    if frame.empty:
        return {
            "total_net_return": 0.0, "total_net_pnl_usd": 0.0,
            "turnover_contracts": 0.0, "transaction_cost_usd": 0.0,
            "max_abs_exposure_contracts": 0.0, "max_drawdown_fraction": 0.0,
            "max_margin_utilization_fraction": 0.0, "trade_count": 0,
        }
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    returns = pd.to_numeric(frame["realized_net_return"], errors="raise").astype(float)
    signal = pd.to_numeric(frame["signal"], errors="raise").astype(float)
    turnover = pd.to_numeric(frame["turnover"], errors="raise").astype(float)
    pnl = returns * float(starting_capital)
    equity = float(starting_capital) + pnl.cumsum()
    equity_before = equity.shift(1).fillna(float(starting_capital)).clip(lower=1e-12)
    peak = equity.cummax().clip(lower=1e-12)
    drawdown = (peak - equity) / peak
    margin_utilization = signal.abs() * float(margin_per_contract) / equity_before
    months = frame["decision_time"].dt.strftime("%Y-%m")
    monthly = returns.groupby(months).sum()
    active_months = int(months.loc[signal.ne(0.0)].nunique())
    return {
        "total_net_return": float(returns.sum()),
        "total_net_pnl_usd": float(pnl.sum()),
        "mean_calendar_month_net_return": float(monthly.mean()) if len(monthly) else 0.0,
        "median_calendar_month_net_return": float(monthly.median()) if len(monthly) else 0.0,
        "profitable_calendar_month_rate": float((monthly > 0.0).mean()) if len(monthly) else 0.0,
        "calendar_month_count": len(monthly),
        "active_month_count": active_months,
        "long_net_return": float(returns.loc[signal > 0.0].sum()),
        "short_net_return": float(returns.loc[signal < 0.0].sum()),
        "flat_net_return": float(returns.loc[signal == 0.0].sum()),
        "turnover_contracts": float(turnover.sum()),
        "transaction_cost_usd": float(turnover.sum() * float(cost_per_side)),
        "trade_count": int(turnover.gt(0.0).sum()),
        "max_abs_exposure_contracts": float(signal.abs().max()),
        "max_drawdown_fraction": float(drawdown.max()),
        "max_margin_utilization_fraction": float(margin_utilization.max()),
        "ending_equity_usd": float(equity.iloc[-1]),
    }


def current_code_identity() -> dict[str, str]:
    return {
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "controller_sha256": sha256_file(REPO / "src/commodity/v2_adaptive_controller.py"),
    }


def validate_code_identity(expected: dict[str, str]) -> None:
    current = current_code_identity()
    if expected != current:
        raise RuntimeError(
            f"issue465 preflight code identity is stale: expected={expected} current={current}"
        )


def build_execution_path(state: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    required_state = {"decision_time", "fill_timestamp", "fill_contract_id", "target_end_timestamp"}
    required_sessions = {"session_open", "next_session_open", "contract_id", "path_move_per_mmbtu"}
    if missing := required_state.difference(state.columns):
        raise RuntimeError(f"issue465 execution state missing columns: {sorted(missing)}")
    if missing := required_sessions.difference(sessions.columns):
        raise RuntimeError(f"issue465 session path missing columns: {sorted(missing)}")
    left = state[list(required_state)].copy()
    right = sessions[list(required_sessions)].copy()
    for column in ("decision_time", "fill_timestamp", "target_end_timestamp"):
        left[column] = pd.to_datetime(left[column], utc=True, errors="raise")
    for column in ("session_open", "next_session_open"):
        right[column] = pd.to_datetime(right[column], utc=True, errors="raise")
    joined = left.merge(right, left_on="fill_timestamp", right_on="session_open", how="left", validate="one_to_one")
    if joined["path_move_per_mmbtu"].isna().any():
        raise RuntimeError("issue465 execution path has unmatched fill timestamps")
    if not joined["fill_contract_id"].astype(str).eq(joined["contract_id"].astype(str)).all():
        raise RuntimeError("issue465 held-contract identity changed at execution join")
    if not joined["target_end_timestamp"].eq(joined["next_session_open"]).all():
        raise RuntimeError("issue465 execution outcome clock changed")
    move = pd.to_numeric(joined["path_move_per_mmbtu"], errors="raise").astype(float)
    if not np.isfinite(move).all():
        raise RuntimeError("issue465 execution path contains non-finite moves")
    out = pd.DataFrame({
        "decision_time": joined["decision_time"],
        "outcome_available_at": joined["next_session_open"],
        "path_move_per_mmbtu": move,
        "fill_timestamp": joined["fill_timestamp"],
        "fill_contract_id": joined["fill_contract_id"].astype(str),
    })
    if not (out["decision_time"] < out["outcome_available_at"]).all():
        raise RuntimeError("issue465 execution outcome is not strictly future to decision")
    return out.sort_values("decision_time").reset_index(drop=True)


def load_scoring_preflight() -> dict[str, object]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue465 scoring requires a written preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue465 scoring requires a clean no-scoring PASS preflight")
    if report.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue465 protected evidence boundary changed")
    identity = report.get("code_identity")
    if not isinstance(identity, dict):
        raise TypeError("issue465 preflight does not bind scoring code identity")
    validate_code_identity({str(k): str(v) for k, v in identity.items()})
    if report.get("prereg_sha256") != sha256_file(PREREG):
        raise RuntimeError("issue465 preregistration changed after preflight")
    artifacts = report.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise TypeError("issue465 preflight artifact identity is missing")
    for name, expected in artifacts.items():
        _verify_file(PROGRAMME / str(name), str(expected), f"preflight artifact {name}")
    return report


def _context_state_for_replay(state: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        column for column in state.columns
        if column != "decision_time" and pd.api.types.is_numeric_dtype(state[column])
    ]
    return state[["decision_time", *numeric]].copy()


def _ledger_payload(ledger: pd.DataFrame, *, freeze_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "freeze_sha256": freeze_sha256,
        "row_count": len(ledger),
        "rows": ledger.to_dict(orient="records"),
    }


def score_block() -> dict[str, object]:
    preflight_report = load_scoring_preflight()
    prereg = load_prereg()
    state, source_evidence = build_pit_state(prereg)
    _features, sessions = load_market_inputs(prereg)
    matrix, metadata, policies = build_policy_matrix(state, prereg)
    archived_state_sha = sha256_file(PIT_STATE)
    expected_state_sha = str(preflight_report["artifact_sha256"][PIT_STATE.name])
    if archived_state_sha != expected_state_sha:
        raise RuntimeError("issue465 PIT state changed after preflight")
    if stable_sha(policies) != str(preflight_report["policy_grid_sha256"]):
        raise RuntimeError("issue465 policy grid changed after preflight")
    path = build_execution_path(state, sessions)
    policy_ids = [column for column in matrix.columns if column != "decision_time"]
    execution = prereg["execution_contract"]
    candidates = candidate_consequence_store(
        matrix,
        path[["decision_time", "outcome_available_at", "path_move_per_mmbtu"]],
        policy_ids,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=float(execution["derived_total_cost_usd_per_contract_side"]),
    )
    expected_rows = len(matrix) * len(policy_ids)
    if len(candidates) != expected_rows:
        raise RuntimeError("issue465 candidate consequence count changed")
    _write_jsonl(CONSEQUENCES, candidates)
    objective_window = int(prereg["selection_contract"]["objective_window_sessions"])
    adaptive = run_adaptive_block(
        matrix,
        path[["decision_time", "outcome_available_at", "path_move_per_mmbtu"]],
        objective_window=objective_window,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=float(execution["derived_total_cost_usd_per_contract_side"]),
        policy_metadata=metadata,
        context_state=_context_state_for_replay(state),
        similar_state_k=int(prereg["comparable_state_contract"]["nearest_prior_states"]),
    )
    _write_json(LEDGER, _ledger_payload(adaptive.ledger, freeze_sha256=adaptive.freeze_sha256))
    eval_times = matrix["decision_time"].iloc[objective_window:].tolist()
    oracle = oracle_diagnostic(candidates, eval_times)
    eval_actual = adaptive.consequences.loc[
        adaptive.consequences["decision_time"].isin(eval_times)
    ].copy()
    total_perf = performance_summary(
        adaptive.consequences,
        starting_capital=float(execution["starting_capital_usd"]),
        cost_per_side=float(execution["derived_total_cost_usd_per_contract_side"]),
        margin_per_contract=float(execution["initial_margin_usd_per_contract"]),
    )
    eval_perf = performance_summary(
        eval_actual,
        starting_capital=float(execution["starting_capital_usd"]),
        cost_per_side=float(execution["derived_total_cost_usd_per_contract_side"]),
        margin_per_contract=float(execution["initial_margin_usd_per_contract"]),
    )
    selected_counts = {
        str(key): int(value)
        for key, value in adaptive.ledger["selected_policy_id"].value_counts().sort_index().items()
    }
    position_counts = {
        str(key): int(value)
        for key, value in adaptive.ledger["position_state"].value_counts().sort_index().items()
    }
    result = {
        "schema_version": 1,
        "issue": 465,
        "block_id": "block-001",
        "status": "BLOCK1_SCORED",
        "scoring_performed": True,
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "policy_grid_sha256": stable_sha(policies),
        "policy_count": len(policy_ids),
        "decision_row_count": len(matrix),
        "candidate_consequence_row_count": len(candidates),
        "adaptive_freeze_sha256": adaptive.freeze_sha256,
        "consequences_sha256": sha256_file(CONSEQUENCES),
        "ledger_sha256": sha256_file(LEDGER),
        "source_evidence": source_evidence,
        "total_block_performance": total_perf,
        "post_warmup_performance": eval_perf,
        "oracle_diagnostic": oracle,
        "oracle_minus_causal_net_return": float(
            oracle["oracle_net_return"] - eval_actual["realized_net_return"].sum()
        ),
        "selected_policy_counts": selected_counts,
        "position_state_counts": position_counts,
        "first_decision_time": matrix["decision_time"].min(),
        "last_decision_time": matrix["decision_time"].max(),
        "objective_window_sessions": objective_window,
        "scoring_code_identity": current_code_identity(),
    }
    _write_json(RESULT, result)
    return result


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"preflight", "score"}:
        raise SystemExit("usage: run_issue465_adaptive_block.py {preflight|score}")
    payload = preflight(write=True) if args[0] == "preflight" else score_block()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
