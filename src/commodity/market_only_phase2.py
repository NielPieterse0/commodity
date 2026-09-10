from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import (
    assumptions_config,
    data_config,
    policy_config,
    simulation_config,
)
from commodity.market_data import (
    build_market_structure_features,
    validate_contract_history,
)
from commodity.models.baselines import HistGradientBoostingReturnModel, RidgeReturnModel
from commodity.phase2_runtime import (
    Phase2CheckpointStore,
    Phase2RuntimeError,
    Phase2Telemetry,
)
from commodity.providers.databento_futures import (
    canonicalize_databento_dbn_partition,
    databento_contract_id,
    decode_databento_dbn_file,
    load_databento_definition_archive,
    map_databento_instrument_symbols,
)
from commodity.rolls import build_derived_continuous_series
from commodity.trading_decision_v0 import (
    ExecutionCostAssumptions,
    PaperRiskPolicy,
    build_decision_origins,
    build_roll_safe_session_path,
    parse_cost_assumptions,
    parse_risk_policy,
    simulate_policy,
)


class Phase2MarketOnlyError(ValueError):
    """Raised when the frozen Phase-2 development contract cannot be satisfied."""


_ARCHIVE_RE = re.compile(
    r"glbx-mdp3-(\d{8})-(\d{8})\.(definition|statistics|ohlcv-1d)\.dbn\.zst$"
)
_LEGACY_RECONSTRUCTION_IMPLEMENTATION_SHA256 = (
    "48d960c2272639406505024192be84b2a57f88baf260b795f69f5d95a16c5142"
)
_LEGACY_INPUT_IMPLEMENTATION_SHA256 = (
    "629817871c6c0d4d3a08e7e84fbb704277f5c29de7386b789aca2440f64794a4"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(payload: object) -> str:
    data = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _callable_bundle_sha256(callables: list[object]) -> str:
    """Fingerprint only the functions/classes that define a reusable stage."""
    payload: dict[str, str] = {}
    for item in callables:
        module = getattr(item, "__module__", "")
        name = getattr(item, "__qualname__", repr(item))
        payload[f"{module}.{name}"] = inspect.getsource(item)
    return _json_sha256(payload)


def _frame_sha256(frame: pd.DataFrame) -> str:
    data = frame.to_csv(
        index=False,
        lineterminator="\n",
        date_format="%Y-%m-%dT%H:%M:%S%z",
        float_format="%.12g",
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _archive_parts(root: Path, schema: str, cutoff: pd.Timestamp) -> dict[str, Path]:
    parts: dict[str, Path] = {}
    for path in sorted((root / schema).glob("*/*.dbn.zst")):
        match = _ARCHIVE_RE.match(path.name)
        if not match or match.group(3) != schema:
            continue
        start, end = match.group(1), match.group(2)
        end_ts = pd.Timestamp(end, tz="UTC")
        if end_ts > cutoff:
            continue
        key = f"{start}-{end}"
        if key in parts:
            raise Phase2MarketOnlyError(
                f"duplicate Databento {schema} partition: {key}"
            )
        parts[key] = path
    if not parts:
        raise Phase2MarketOnlyError(
            f"no Databento {schema} partitions found before cutoff"
        )
    return parts


def _build_executable_selected_path(
    selected_raw: pd.DataFrame,
    execution_bars: pd.DataFrame,
) -> pd.DataFrame:
    """Map PIT roll decisions to strictly later UTC-day OHLCV interval opens."""
    decisions = selected_raw[
        ["trade_date", "contract_id", "expiration", "roll_reason", "available_at"]
    ].copy()
    decisions["selection_source_trade_date"] = pd.to_datetime(
        decisions.pop("trade_date"), utc=True
    )
    decisions["available_at"] = pd.to_datetime(decisions["available_at"], utc=True)

    intervals = execution_bars[["trade_date"]].drop_duplicates().copy()
    intervals["trade_date"] = pd.to_datetime(intervals["trade_date"], utc=True)
    intervals["session_open"] = intervals["trade_date"].dt.normalize()
    if intervals["session_open"].duplicated().any():
        raise Phase2MarketOnlyError("UTC-day execution interval opens must be unique")

    desired = pd.merge_asof(
        intervals.sort_values("session_open"),
        decisions.sort_values("available_at"),
        left_on="session_open",
        right_on="available_at",
        direction="backward",
        allow_exact_matches=False,
    ).dropna(subset=["contract_id"])
    if desired.empty:
        raise Phase2MarketOnlyError(
            "no selected contract is knowable before a retained UTC-day interval open"
        )

    available = set(
        zip(
            pd.to_datetime(execution_bars["trade_date"], utc=True),
            execution_bars["contract_id"].astype(str),
            strict=True,
        )
    )
    records: list[dict[str, Any]] = []
    held_contract: str | None = None
    segment_id = 0
    for row in desired.sort_values("session_open").itertuples(index=False):
        trade_date = pd.Timestamp(row.trade_date)
        desired_contract = str(row.contract_id)
        if (trade_date, desired_contract) not in available:
            continue
        starts_new_segment = held_contract is None or (
            held_contract != desired_contract and (trade_date, held_contract) not in available
        )
        if starts_new_segment:
            segment_id += 1
        record = row._asdict()
        record["contract_id"] = desired_contract
        record["segment_id"] = segment_id
        records.append(record)
        held_contract = desired_contract

    selected = pd.DataFrame.from_records(records)
    if selected.empty:
        raise Phase2MarketOnlyError(
            "no exact-contract UTC-day execution path can be reconstructed"
        )
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True)
    selected["session_open"] = pd.to_datetime(selected["session_open"], utc=True)
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    if (selected["available_at"] >= selected["session_open"]).any():
        raise Phase2MarketOnlyError(
            "selected contract crossed its strict executable information boundary"
        )
    return selected.reset_index(drop=True)


def _target_ohlcv(definitions: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    target_defs = definitions.loc[
        definitions["asset"].astype(str).eq("NG")
        & definitions["instrument_class"].astype(str).eq("F")
    ].copy()
    target_ids = set(
        pd.to_numeric(target_defs["instrument_id"], errors="coerce")
        .dropna()
        .astype("uint64")
    )
    observations = bars.loc[
        pd.to_numeric(bars["instrument_id"], errors="coerce").isin(target_ids)
    ].copy()
    if observations.empty:
        raise Phase2MarketOnlyError("OHLCV partition contains no NG outright futures")
    definition_time = "ts_recv" if "ts_recv" in target_defs.columns else "ts_event"
    first_definition = (
        target_defs.assign(
            _definition_time=pd.to_datetime(
                target_defs[definition_time], utc=True, errors="coerce"
            )
        )
        .groupby("instrument_id")["_definition_time"]
        .min()
    )
    observation_time = pd.to_datetime(
        observations["ts_event"], utc=True, errors="coerce"
    )
    first_seen = pd.to_datetime(
        observations["instrument_id"].map(first_definition), utc=True, errors="coerce"
    )
    observations = observations.loc[
        first_seen.notna() & observation_time.ge(first_seen)
    ].copy()
    mapped = map_databento_instrument_symbols(target_defs, observations)
    mapped = mapped.loc[
        mapped["definition_asset"].astype(str).eq("NG")
        & mapped["definition_instrument_class"].astype(str).eq("F")
    ].copy()
    mapped["expiration"] = pd.to_datetime(
        mapped["definition_expiration"], utc=True, errors="coerce"
    )
    mapped["trade_date"] = pd.to_datetime(
        mapped["ts_event"], utc=True, errors="coerce"
    ).dt.normalize()
    mapped["contract_id"] = databento_contract_id(
        mapped["symbol"], mapped["expiration"]
    )
    for column in ("open", "high", "low", "close", "volume"):
        mapped[column] = pd.to_numeric(mapped[column], errors="coerce")
    required = [
        "trade_date",
        "contract_id",
        "expiration",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    if mapped[required].isna().any().any():
        raise Phase2MarketOnlyError("mapped NG OHLCV contains invalid required values")
    if (mapped[["open", "high", "low", "close"]] <= 0).any().any() or (
        mapped["volume"] < 0
    ).any():
        raise Phase2MarketOnlyError(
            "mapped NG OHLCV contains invalid price or volume values"
        )
    out = mapped[required].sort_values(
        ["trade_date", "expiration", "contract_id"], kind="stable"
    )
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise Phase2MarketOnlyError(
            "mapped NG OHLCV is not unique by trade_date/contract_id"
        )
    return out.reset_index(drop=True)


def reconstruct_market_history(
    databento_root: Path,
    cfg: dict[str, Any],
    *,
    checkpoint_store: Phase2CheckpointStore | None = None,
    telemetry: Phase2Telemetry | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    telemetry = telemetry or Phase2Telemetry(None, echo=False)
    boundary = cfg["evidence_boundary"]
    cutoff = pd.Timestamp(boundary["last_allowed_trade_date"], tz="UTC")
    root = Path(databento_root)
    partitions = {
        schema_name: _archive_parts(root, schema_name, cutoff)
        for schema_name in ("definition", "statistics", "ohlcv-1d")
    }
    keys = sorted(
        set(partitions["definition"])
        & set(partitions["statistics"])
        & set(partitions["ohlcv-1d"])
    )
    base_keys = set(keys)
    if not keys or any(set(partitions[name]) != base_keys for name in partitions):
        raise Phase2MarketOnlyError(
            "Databento Phase-2 partitions do not have complete definition/statistics/OHLCV triples"
        )

    source_hashes: dict[str, dict[str, str]] = {
        schema_name: {} for schema_name in partitions
    }
    total_files = len(keys) * len(partitions)
    completed = 0
    with telemetry.stage("source_integrity", files=total_files):
        for schema_name in ("definition", "statistics", "ohlcv-1d"):
            for key in keys:
                path = partitions[schema_name][key]
                digest = _sha256_file(path)
                source_hashes[schema_name][key] = digest
                completed += 1
                telemetry.event(
                    "source_hashed",
                    stage="source_integrity",
                    schema=schema_name,
                    partition=key,
                    completed=completed,
                    total=total_files,
                    sha256=digest,
                )

    schema = data_config()["canonical_contract_schema"]
    definition_identity = {
        "cache_version": 1,
        "kind": "global_ng_definition_authority",
        "product_code": "NG",
        "definition_sources": source_hashes["definition"],
    }
    definitions = None
    definition_authority = None
    if checkpoint_store is not None:
        definitions = checkpoint_store.load_frame(
            "reconstruction/definitions", definition_identity
        )
        definition_authority = checkpoint_store.load_json(
            "reconstruction/definition-authority", definition_identity
        )
    if definitions is None or definition_authority is None:
        definition_paths = [partitions["definition"][key] for key in keys]
        with telemetry.stage(
            "definition_archive_decode", partitions=len(definition_paths)
        ):
            definitions, definition_authority = load_databento_definition_archive(
                definition_paths,
                product_code="NG",
            )
        if checkpoint_store is not None:
            checkpoint_store.save_frame(
                "reconstruction/definitions", definitions, definition_identity
            )
            checkpoint_store.save_json(
                "reconstruction/definition-authority",
                definition_authority,
                definition_identity,
            )
    definition_artifacts = {
        str(item["source_file"]): item
        for item in definition_authority["definition_artifacts"]
    }

    canonical_parts: list[pd.DataFrame] = []
    ohlcv_parts: list[pd.DataFrame] = []
    sources: list[dict[str, object]] = []
    for index, key in enumerate(keys, start=1):
        definition_path = partitions["definition"][key]
        statistics_path = partitions["statistics"][key]
        ohlcv_path = partitions["ohlcv-1d"][key]
        definition_provenance = definition_artifacts.get(definition_path.name)
        if not isinstance(definition_provenance, dict):
            raise Phase2MarketOnlyError(
                f"definition provenance is missing for partition: {key}"
            )
        if (
            definition_provenance.get("source_sha256")
            != source_hashes["definition"][key]
        ):
            raise Phase2MarketOnlyError(f"definition source hash mismatch: {key}")
        partition_identity = {
            "cache_version": 1,
            "partition": key,
            "canonical_schema_sha256": _json_sha256(schema),
            "definition_authority_sha256": str(
                definition_authority["definition_authority_sha256"]
            ),
            "statistics_source_sha256": source_hashes["statistics"][key],
            "ohlcv_source_sha256": source_hashes["ohlcv-1d"][key],
        }
        cache_prefix = f"reconstruction/partitions/{key}"
        canonical = None
        ohlcv_part = None
        if checkpoint_store is not None:
            canonical = checkpoint_store.load_frame(
                f"{cache_prefix}-canonical", partition_identity
            )
            ohlcv_part = checkpoint_store.load_frame(
                f"{cache_prefix}-ohlcv", partition_identity
            )
        if canonical is None or ohlcv_part is None:
            with telemetry.stage(
                "partition_reconstruction",
                partition=key,
                index=index,
                total=len(keys),
            ):
                canonical, statistics_meta = canonicalize_databento_dbn_partition(
                    definitions,
                    statistics_path,
                    schema=schema,
                    product_code="NG",
                    retrieved_at="2026-08-13T16:35:30Z",
                    definition_authority_sha256=str(
                        definition_authority["definition_authority_sha256"]
                    ),
                )
                bars, ohlcv_provenance = decode_databento_dbn_file(
                    ohlcv_path, expected_schema="ohlcv-1d"
                )
                ohlcv_part = _target_ohlcv(definitions, bars)
                statistics_artifact = statistics_meta["statistics_artifact"]
                if (
                    statistics_artifact.get("source_sha256")
                    != source_hashes["statistics"][key]
                ):
                    raise Phase2MarketOnlyError(
                        f"statistics source hash mismatch: {key}"
                    )
                if (
                    ohlcv_provenance.get("source_sha256")
                    != source_hashes["ohlcv-1d"][key]
                ):
                    raise Phase2MarketOnlyError(f"OHLCV source hash mismatch: {key}")
            if checkpoint_store is not None:
                checkpoint_store.save_frame(
                    f"{cache_prefix}-canonical", canonical, partition_identity
                )
                checkpoint_store.save_frame(
                    f"{cache_prefix}-ohlcv", ohlcv_part, partition_identity
                )
        canonical_parts.append(canonical)
        ohlcv_parts.append(ohlcv_part)
        sources.append(
            {
                "partition": key,
                "definition": {
                    "file": definition_path.name,
                    "sha256": source_hashes["definition"][key],
                },
                "statistics": {
                    "file": statistics_path.name,
                    "sha256": source_hashes["statistics"][key],
                },
                "ohlcv_1d": {
                    "file": ohlcv_path.name,
                    "sha256": source_hashes["ohlcv-1d"][key],
                },
            }
        )
        telemetry.event(
            "partition_ready",
            stage="reconstruction",
            partition=key,
            completed=index,
            total=len(keys),
        )

    with telemetry.stage("reconstruction_assemble", partitions=len(keys)):
        canonical = pd.concat(canonical_parts, ignore_index=True)
        canonical = canonical.sort_values(
            ["trade_date", "expiration", "contract_id"], kind="stable"
        )
        canonical = canonical.drop_duplicates(
            ["trade_date", "contract_id"], keep="last"
        ).reset_index(drop=True)
        canonical = validate_contract_history(canonical, schema)
        if pd.Timestamp(canonical["trade_date"].max()) > cutoff:
            raise Phase2MarketOnlyError(
                "canonical market history crossed the protected Phase-2 cutoff"
            )
        ohlcv = pd.concat(ohlcv_parts, ignore_index=True)
        ohlcv = ohlcv.sort_values(
            ["trade_date", "expiration", "contract_id"], kind="stable"
        )
        ohlcv = ohlcv.drop_duplicates(
            ["trade_date", "contract_id"], keep="last"
        ).reset_index(drop=True)
        ohlcv_market = ohlcv[
            ["trade_date", "contract_id", "open", "high", "low", "close", "volume"]
        ].rename(columns={"volume": "ohlcv_volume"})
        market = canonical.merge(
            ohlcv_market,
            on=["trade_date", "contract_id"],
            how="inner",
            validate="one_to_one",
        )
        if market.empty:
            raise Phase2MarketOnlyError(
                "exact-contract settlement/OHLCV feature join is empty"
            )
        execution_bars = ohlcv.copy()
        if execution_bars.empty:
            raise Phase2MarketOnlyError("exact-contract UTC-day OHLCV execution history is empty")
        if pd.Timestamp(execution_bars["trade_date"].max()) > cutoff:
            raise Phase2MarketOnlyError(
                "UTC-day OHLCV execution history crossed the protected Phase-2 cutoff"
            )
    provenance = {
        "source_id": "databento_henry_hub_pre2023_phase2",
        "source_root_role": "local_retained_nonredistributable_raw_snapshot",
        "partitions": sources,
        "canonical_rows": len(canonical),
        "ohlcv_feature_join_rows": len(market),
        "utc_day_execution_rows": len(execution_bars),
        "start_trade_date": pd.Timestamp(market["trade_date"].min()).date().isoformat(),
        "end_trade_date": pd.Timestamp(market["trade_date"].max()).date().isoformat(),
        "canonical_content_sha256": _frame_sha256(canonical),
        "market_content_sha256": _frame_sha256(market),
        "execution_bars_content_sha256": _frame_sha256(execution_bars),
        "execution_price_semantics": "databento_ohlcv_1d_utc_interval_open",
        "ohlcv_semantics": "utc_day_bars; execution only at strictly later interval boundary; features after trade_date_2359_utc",
    }
    provenance["provenance_sha256"] = _json_sha256(provenance)
    return canonical, market, execution_bars, provenance


def _validate_executable_selected(
    selected: pd.DataFrame, execution_bars: pd.DataFrame
) -> pd.DataFrame:
    """Require exact open prices for each held interval and each next-close interval."""
    selected = selected.sort_values("trade_date").reset_index(drop=True)
    keys = set(
        zip(
            pd.to_datetime(execution_bars["trade_date"], utc=True),
            execution_bars["contract_id"].astype(str),
            strict=True,
        )
    )
    if "segment_id" not in selected.columns:
        raise Phase2MarketOnlyError("segmented execution path is missing segment identity")
    for _, segment in selected.groupby("segment_id", sort=False):
        segment = segment.reset_index(drop=True)
        for index, row in segment.iterrows():
            current_key = (pd.Timestamp(row["trade_date"]), str(row["contract_id"]))
            if current_key not in keys:
                raise Phase2MarketOnlyError(
                    f"selected UTC-day execution open is missing: {current_key}"
                )
            if index + 1 < len(segment):
                next_date = pd.Timestamp(segment.iloc[index + 1]["trade_date"])
                next_key = (next_date, str(row["contract_id"]))
                if next_key not in keys:
                    raise Phase2MarketOnlyError(
                        f"same-contract next UTC-day open is missing: {next_key}"
                    )
    return selected


def build_phase2_inputs(
    canonical: pd.DataFrame,
    market: pd.DataFrame,
    execution_bars: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    telemetry: Phase2Telemetry | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    telemetry = telemetry or Phase2Telemetry(None, echo=False)
    schema = data_config()["canonical_contract_schema"]
    roll_policy = assumptions_config()["assumptions"]["continuous_series_policy"][
        "policy"
    ]
    selected_raw, _ = build_derived_continuous_series(
        canonical, schema, roll_policy, price_col="settle"
    )
    selected_raw = selected_raw.sort_values("trade_date").reset_index(drop=True)
    telemetry.event(
        "input_roll_decisions",
        rows=len(selected_raw),
        first_trade_date=str(pd.Timestamp(selected_raw["trade_date"].min()).date()),
        last_trade_date=str(pd.Timestamp(selected_raw["trade_date"].max()).date()),
    )
    execution = cfg["execution_contract"]
    if roll_policy.get("method") != execution["roll_policy"]:
        raise Phase2MarketOnlyError(
            "Phase-2 roll policy disagrees with the inherited Phase-1 contract"
        )
    selected = _build_executable_selected_path(selected_raw, execution_bars)
    selected = _validate_executable_selected(selected, execution_bars)
    path_parts: list[pd.DataFrame] = []
    for segment_id, segment in selected.groupby("segment_id", sort=False):
        if len(segment) < 2:
            continue
        part = build_roll_safe_session_path(
            execution_bars, segment, price_col="open"
        )
        part["segment_id"] = int(segment_id)
        path_parts.append(part)
    if not path_parts:
        raise Phase2MarketOnlyError("no multi-interval execution segments are available")
    session_path = pd.concat(path_parts, ignore_index=True).sort_values("trade_date").reset_index(drop=True)
    segment_sizes = session_path.groupby("segment_id", sort=False).size()
    telemetry.event(
        "input_execution_path",
        selected_rows=len(selected),
        session_path_rows=len(session_path),
        segment_count=int(segment_sizes.size),
        segments_with_five_moves=int((segment_sizes >= 6).sum()),
        first_trade_date=str(pd.Timestamp(session_path["trade_date"].min()).date()),
        last_trade_date=str(pd.Timestamp(session_path["trade_date"].max()).date()),
    )

    technical = market.sort_values(["contract_id", "trade_date"], kind="stable").copy()
    technical["log_settle"] = np.log(technical["settle"].astype(float))
    grouped = technical.groupby("contract_id", group_keys=False)
    technical["feature_ret_1"] = grouped["log_settle"].diff(1)
    technical["feature_ret_5"] = grouped["log_settle"].diff(5)
    technical["feature_ret_20"] = grouped["log_settle"].diff(20)
    technical["feature_vol_5"] = (
        grouped["feature_ret_1"].rolling(5).std().reset_index(level=0, drop=True)
    )
    technical["feature_vol_20"] = (
        grouped["feature_ret_1"].rolling(20).std().reset_index(level=0, drop=True)
    )
    technical["feature_ma_gap_5"] = (
        technical["settle"]
        / grouped["settle"].rolling(5).mean().reset_index(level=0, drop=True)
        - 1.0
    )
    technical["feature_ma_gap_20"] = (
        technical["settle"]
        / grouped["settle"].rolling(20).mean().reset_index(level=0, drop=True)
        - 1.0
    )
    technical["feature_range_pct"] = (
        technical["high"].astype(float) - technical["low"].astype(float)
    ) / technical["close"].astype(float)

    selected_features = selected[
        ["trade_date", "contract_id", "expiration", "roll_reason"]
    ].merge(
        technical,
        on=["trade_date", "contract_id", "expiration"],
        how="inner",
        validate="one_to_one",
    )
    if selected_features.empty:
        raise Phase2MarketOnlyError("no PIT market-only feature origins overlap the execution path")
    telemetry.event(
        "input_technical_origins",
        rows=len(selected_features),
        technical_rows=len(technical),
    )
    dates = pd.to_datetime(selected_features["trade_date"], utc=True)
    angle = 2.0 * np.pi * dates.dt.dayofyear.astype(float) / 365.25
    selected_features["feature_season_sin"] = np.sin(angle)
    selected_features["feature_season_cos"] = np.cos(angle)
    selected_features["feature_selected_dte"] = (
        pd.to_datetime(selected_features["expiration"], utc=True).dt.normalize()
        - dates.dt.normalize()
    ).dt.days.astype(float)
    selected_features["feature_roll_event"] = (
        ~selected_features["roll_reason"].isin(["hold", "initial"])
    ).astype(float)

    stats_available = (
        canonical.assign(
            available_at=pd.to_datetime(canonical["available_at"], utc=True)
        )
        .groupby("trade_date", as_index=False)["available_at"]
        .max()
    )
    stats_available["ohlcv_available_at"] = pd.to_datetime(
        stats_available["trade_date"], utc=True
    ).dt.normalize() + pd.Timedelta(hours=23, minutes=59)
    stats_available["feature_available_at"] = stats_available[
        ["available_at", "ohlcv_available_at"]
    ].max(axis=1)
    selected_features = selected_features.merge(
        stats_available[["trade_date", "feature_available_at"]],
        on="trade_date",
        how="inner",
        validate="one_to_one",
    )
    if selected_features.empty:
        raise Phase2MarketOnlyError("market-only feature availability produced no PIT origins")
    telemetry.event(
        "input_pit_origins",
        rows=len(selected_features),
        availability_rows=len(stats_available),
    )

    cutoffs = selected_features[["trade_date", "feature_available_at"]].rename(
        columns={"feature_available_at": "prediction_time"}
    )
    curve_source = market.drop(columns=["volume"]).rename(
        columns={"ohlcv_volume": "volume"}
    )
    curve_source["available_at"] = curve_source[
        ["available_at"]
    ].max(axis=1)
    curve_source["available_at"] = pd.concat(
        [
            pd.to_datetime(curve_source["available_at"], utc=True),
            pd.to_datetime(curve_source["trade_date"], utc=True).dt.normalize()
            + pd.Timedelta(hours=23, minutes=59),
        ],
        axis=1,
    ).max(axis=1)
    curve, _ = build_market_structure_features(
        curve_source,
        schema,
        cutoffs,
        max_contracts=4,
    )
    curve = curve.reset_index()
    curve = curve.merge(
        cutoffs,
        on="prediction_time",
        how="left",
        validate="one_to_one",
    )
    telemetry.event(
        "input_curve_rows",
        requested_cutoffs=len(cutoffs),
        curve_rows=len(curve),
    )
    for rank in range(1, 5):
        settle_col = f"curve_settle_m{rank}"
        volume_col = f"curve_volume_m{rank}"
        curve[f"feature_curve_log_settle_m{rank}"] = np.log(
            pd.to_numeric(curve[settle_col], errors="coerce")
        )
        curve[f"feature_curve_log_volume_m{rank}"] = np.log1p(
            pd.to_numeric(curve[volume_col], errors="coerce")
        )
        curve[f"feature_curve_dte_m{rank}"] = pd.to_numeric(
            curve[f"curve_dte_m{rank}"], errors="coerce"
        )
    for rank in range(1, 4):
        curve[f"feature_curve_spread_m{rank}_m{rank + 1}"] = pd.to_numeric(
            curve[f"curve_spread_m{rank}_m{rank + 1}"], errors="coerce"
        )
    curve["feature_curve_slope_m1_m4"] = pd.to_numeric(
        curve["curve_slope_m1_m4"], errors="coerce"
    )
    curve["feature_curve_volume_ratio_m1_m2"] = pd.to_numeric(
        curve["curve_volume_ratio_m1_m2"], errors="coerce"
    )
    curve_features = [
        column for column in curve.columns if column.startswith("feature_curve_")
    ]
    features = selected_features.merge(
        curve[["trade_date", *curve_features]],
        on="trade_date",
        how="left",
        validate="one_to_one",
    )
    configured = sorted(
        {column for columns in cfg["feature_sets"].values() for column in columns}
    )
    missing = sorted(set(configured) - set(features.columns))
    if missing:
        raise Phase2MarketOnlyError(
            f"configured Phase-2 features are unavailable: {missing}"
        )
    features = features.replace([np.inf, -np.inf], np.nan)
    missing_counts = {column: int(features[column].isna().sum()) for column in configured}
    complete_rows = int(features[configured].notna().all(axis=1).sum())
    telemetry.event(
        "input_feature_completeness",
        rows=len(features),
        complete_rows=complete_rows,
        all_missing_features=sorted(
            column for column, count in missing_counts.items() if count == len(features)
        ),
        missing_counts=missing_counts,
    )
    features = features.dropna(subset=configured).copy()
    features = features[["trade_date", "feature_available_at", *configured]].rename(
        columns={"feature_available_at": "available_at"}
    )
    cutoff = pd.Timestamp(cfg["evidence_boundary"]["last_allowed_trade_date"], tz="UTC")
    if features.empty or pd.Timestamp(features["trade_date"].max()) > cutoff:
        raise Phase2MarketOnlyError(
            "Phase-2 feature frame is empty or crosses the protected cutoff"
        )
    telemetry.event(
        "input_features_ready",
        rows=len(features),
        first_trade_date=str(pd.Timestamp(features["trade_date"].min()).date()),
        last_trade_date=str(pd.Timestamp(features["trade_date"].max()).date()),
    )
    return session_path, features.reset_index(drop=True)


def validate_phase2_config(cfg: dict[str, Any]) -> None:
    boundary = cfg.get("evidence_boundary", {})
    if boundary.get("protected_confirmation_accessed") is not False:
        raise Phase2MarketOnlyError(
            "protected confirmation must remain unopened in Phase 2"
        )
    cutoff = pd.to_datetime(
        boundary.get("last_allowed_trade_date"), utc=True, errors="coerce"
    )
    if pd.isna(cutoff) or pd.Timestamp(cutoff) > pd.Timestamp("2022-12-31T23:59:59Z"):
        raise Phase2MarketOnlyError(
            "Phase-2 evidence must end no later than 2022-12-31"
        )
    execution = cfg.get("execution_contract", {})
    if int(execution.get("horizon_sessions", 0)) != 5:
        raise Phase2MarketOnlyError(
            "Phase-2 must preserve the inherited five-session target"
        )
    if execution.get("ohlcv_available_at_method") != "trade_date_2359_utc":
        raise Phase2MarketOnlyError(
            "Phase-2 must preserve the conservative OHLCV availability bound"
        )
    if (
        execution.get("ohlcv_role")
        != "utc_day_features_and_strictly_later_interval_execution"
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 UTC-day OHLCV role disagrees with amended L3 authority"
        )
    if (
        execution.get("execution_open_price_source")
        != "databento_ohlcv_1d_utc_interval_open"
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 execution must use retained UTC-day OHLCV interval opens"
        )
    if execution.get("execution_open_schema") != "ohlcv-1d":
        raise Phase2MarketOnlyError("Phase-2 execution opening schema must be ohlcv-1d")
    if (
        execution.get("execution_open_rule")
        != "first_retained_interval_open_strictly_after_all_inputs_available"
    ):
        raise Phase2MarketOnlyError("Phase-2 UTC-day execution rule must remain frozen")
    if (
        execution.get("execution_open_missing_policy")
        != "skip_non_executable_interval_no_synthetic_fill"
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 missing execution bars must fail closed without synthetic fills"
        )
    if (
        execution.get("fill_clock")
        != "first_eligible_utc_day_interval_open_strictly_after_all_inputs_available"
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 fill clock must wait for a strictly later eligible UTC-day interval"
        )
    feature_sets = cfg.get("feature_sets")
    candidates = cfg.get("candidates")
    if not isinstance(feature_sets, dict) or not feature_sets:
        raise Phase2MarketOnlyError("Phase-2 feature sets are missing")
    if not isinstance(candidates, list) or not candidates:
        raise Phase2MarketOnlyError("Phase-2 candidate grid is missing")
    ids = [str(item.get("id", "")) for item in candidates if isinstance(item, dict)]
    if (
        len(ids) != len(candidates)
        or len(set(ids)) != len(ids)
        or any(not item for item in ids)
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 candidate IDs must be non-empty and unique"
        )
    for candidate in candidates:
        if candidate.get("feature_set") not in feature_sets:
            raise Phase2MarketOnlyError(
                "Phase-2 candidate references an unknown feature set"
            )


def _candidate_model(candidate: dict[str, Any]) -> object | None:
    model = str(candidate["model"])
    params = dict(candidate.get("parameters", {}))
    if model in {"zero", "expanding_mean"}:
        return None
    if model == "ridge":
        return RidgeReturnModel(alpha=float(params.get("alpha", 10.0)))
    if model == "hist_gb":
        return HistGradientBoostingReturnModel(
            learning_rate=float(params.get("learning_rate", 0.05)),
            max_iter=int(params.get("max_iter", 20)),
            max_leaf_nodes=int(params.get("max_leaf_nodes", 15)),
            random_state=int(params.get("random_state", 0)),
        )
    raise Phase2MarketOnlyError(f"unsupported Phase-2 candidate model: {model}")


def _forecast_id(candidate_id: str, fill_timestamp: pd.Timestamp) -> str:
    payload = f"phase2-market-only-v1\0{candidate_id}\0{fill_timestamp.isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def forecast_candidate_window(
    origins: pd.DataFrame,
    candidate: dict[str, Any],
    feature_columns: list[str],
    *,
    start_timestamp: pd.Timestamp,
    boundary_timestamp: pd.Timestamp,
    contract_multiplier: float,
    min_train_rows: int,
    horizon_sessions: int,
) -> pd.DataFrame:
    start = pd.Timestamp(start_timestamp)
    boundary = pd.Timestamp(boundary_timestamp)
    if start.tzinfo is None or boundary.tzinfo is None or boundary <= start:
        raise Phase2MarketOnlyError(
            "candidate window requires ordered timezone-aware boundaries"
        )
    frame = origins.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if (
        frame[["signal_timestamp", "fill_timestamp", "target_end_timestamp"]]
        .isna()
        .any()
        .any()
    ):
        raise Phase2MarketOnlyError("candidate origins contain invalid timestamps")
    training = frame.loc[frame["target_end_timestamp"] < start].copy()
    evaluation = frame.loc[
        frame["fill_timestamp"].ge(start) & frame["target_end_timestamp"].lt(boundary)
    ].copy()
    if len(training) < min_train_rows:
        raise Phase2MarketOnlyError(
            f"candidate window has {len(training)} training rows; requires {min_train_rows}"
        )
    if evaluation.empty:
        raise Phase2MarketOnlyError(
            "candidate window has no purge-safe evaluation origins"
        )
    if any(column not in frame.columns for column in feature_columns):
        raise Phase2MarketOnlyError("candidate feature set is incomplete")
    x_train = training[feature_columns]
    y_train = training["target_path_move_per_mmbtu"].astype(float)
    x_eval = evaluation[feature_columns]
    model_name = str(candidate["model"])
    fitted = _candidate_model(candidate)
    if model_name == "zero":
        prediction = np.zeros(len(evaluation), dtype=float)
        train_prediction = np.zeros(len(training), dtype=float)
    elif model_name == "expanding_mean":
        mean_value = float(y_train.mean())
        prediction = np.full(len(evaluation), mean_value, dtype=float)
        train_prediction = np.full(len(training), mean_value, dtype=float)
    else:
        assert fitted is not None
        fitted.fit(x_train, y_train)
        prediction = fitted.predict(x_eval).to_numpy(dtype=float)
        train_prediction = fitted.predict(x_train).to_numpy(dtype=float)
    residual = y_train.to_numpy(dtype=float) - train_prediction
    uncertainty = float(np.std(residual, ddof=1)) if len(residual) > 1 else 0.0
    if not math.isfinite(uncertainty):
        uncertainty = 0.0
    latest_training_end = pd.Timestamp(training["target_end_timestamp"].max())
    if latest_training_end >= start:
        raise Phase2MarketOnlyError(
            "candidate training target overlaps its evaluation boundary"
        )

    output = evaluation.copy()
    output["candidate_id"] = str(candidate["id"])
    output["model_id"] = str(candidate["id"])
    output["prediction"] = prediction
    output["predicted_path_move_per_mmbtu"] = prediction
    output["predicted_gross_pnl_usd"] = prediction * float(contract_multiplier)
    output["uncertainty_per_mmbtu"] = uncertainty
    output["uncertainty_usd"] = uncertainty * float(contract_multiplier)
    output["actual_path_move_per_mmbtu"] = output["target_path_move_per_mmbtu"].astype(
        float
    )
    output["actual_gross_pnl_usd"] = output["actual_path_move_per_mmbtu"] * float(
        contract_multiplier
    )
    output["training_rows"] = len(training)
    output["latest_training_target_end"] = latest_training_end
    output["horizon_sessions"] = int(horizon_sessions)
    output["forecast_id"] = [
        _forecast_id(str(candidate["id"]), pd.Timestamp(value))
        for value in output["fill_timestamp"]
    ]
    required = [
        "forecast_id",
        "model_id",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "fill_contract_id",
        "target_end_timestamp",
        "latest_training_target_end",
        "training_rows",
        "prediction",
        "predicted_path_move_per_mmbtu",
        "predicted_gross_pnl_usd",
        "uncertainty_per_mmbtu",
        "uncertainty_usd",
        "actual_path_move_per_mmbtu",
        "actual_gross_pnl_usd",
        "horizon_sessions",
    ]
    return output[required].sort_values("fill_timestamp").reset_index(drop=True)


def select_best_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise Phase2MarketOnlyError("candidate selection requires scored candidates")
    required = {
        "candidate_id",
        "net_pnl_usd",
        "transaction_cost_usd",
        "simplicity_rank",
    }
    for row in rows:
        if not required.issubset(row):
            raise Phase2MarketOnlyError("candidate score is incomplete")
    return min(
        rows,
        key=lambda row: (
            -float(row["net_pnl_usd"]),
            float(row["transaction_cost_usd"]),
            int(row["simplicity_rank"]),
            str(row["candidate_id"]),
        ),
    )


def _risk_adjusted_diagnostics(
    ledger: pd.DataFrame, starting_capital_usd: float
) -> dict[str, float | None]:
    daily = ledger["net_pnl_usd"].to_numpy(dtype=float) / float(starting_capital_usd)
    mean = float(np.mean(daily)) if len(daily) else 0.0
    std = float(np.std(daily, ddof=1)) if len(daily) > 1 else 0.0
    downside = daily[daily < 0.0]
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    max_drawdown = float(ledger["drawdown_fraction"].max()) if len(ledger) else 0.0
    total_return = float(ledger["net_pnl_usd"].sum()) / float(starting_capital_usd)
    return {
        "sharpe": None if std <= 0.0 else float(np.sqrt(252.0) * mean / std),
        "sortino": None
        if downside_std <= 0.0
        else float(np.sqrt(252.0) * mean / downside_std),
        "calmar": None if max_drawdown <= 0.0 else total_return / max_drawdown,
    }


def summarize_ledger(
    ledger: pd.DataFrame,
    *,
    starting_capital_usd: float,
) -> dict[str, Any]:
    required = {
        "target_position",
        "gross_pnl_usd",
        "transaction_cost_usd",
        "net_pnl_usd",
        "drawdown_fraction",
        "execution_side_count",
    }
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise Phase2MarketOnlyError(f"Phase-2 ledger is missing diagnostics: {missing}")

    def side_summary(mask: pd.Series) -> dict[str, float | int]:
        part = ledger.loc[mask]
        return {
            "sessions": len(part),
            "gross_pnl_usd": float(part["gross_pnl_usd"].sum()),
            "transaction_cost_usd": float(part["transaction_cost_usd"].sum()),
            "net_pnl_usd": float(part["net_pnl_usd"].sum()),
        }

    result: dict[str, Any] = {
        "net_pnl_usd": float(ledger["net_pnl_usd"].sum()),
        "transaction_cost_usd": float(ledger["transaction_cost_usd"].sum()),
        "execution_side_count": int(ledger["execution_side_count"].sum()),
        "max_drawdown_fraction": float(ledger["drawdown_fraction"].max())
        if len(ledger)
        else 0.0,
        "max_abs_contracts": int(ledger["target_position"].abs().max())
        if len(ledger)
        else 0,
        "long": side_summary(ledger["target_position"] > 0),
        "short": side_summary(ledger["target_position"] < 0),
        "flat": side_summary(ledger["target_position"] == 0),
    }
    result.update(_risk_adjusted_diagnostics(ledger, starting_capital_usd))
    return result


def _forecast_diagnostics(forecasts: pd.DataFrame) -> dict[str, float | int]:
    prediction = forecasts["prediction"].to_numpy(dtype=float)
    actual = forecasts["actual_path_move_per_mmbtu"].to_numpy(dtype=float)
    error = prediction - actual
    nonzero = np.sign(prediction) != 0
    direction = (
        float(np.mean(np.sign(prediction[nonzero]) == np.sign(actual[nonzero])))
        if nonzero.any()
        else 0.0
    )
    return {
        "forecasts": len(forecasts),
        "rmse_per_mmbtu": float(np.sqrt(np.mean(error**2))),
        "mae_per_mmbtu": float(np.mean(np.abs(error))),
        "direction_accuracy_nonzero": direction,
        "nonzero_forecasts": int(nonzero.sum()),
    }


def _candidate_by_id(cfg: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    matches = [item for item in cfg["candidates"] if item["id"] == candidate_id]
    if len(matches) != 1:
        raise Phase2MarketOnlyError(f"unknown or duplicate candidate: {candidate_id}")
    return matches[0]


def _path_window(
    path: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    ordered = path.sort_values("trade_date").reset_index(drop=True)
    dates = pd.to_datetime(ordered["trade_date"], utc=True)
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    start_positions = np.flatnonzero(dates.ge(start).to_numpy())
    if not len(start_positions):
        raise Phase2MarketOnlyError(f"window starts after available path: {start_date}")
    start_index = int(start_positions[0])
    boundary_positions = np.flatnonzero(dates.gt(end).to_numpy())
    if len(boundary_positions):
        boundary_index = int(boundary_positions[0])
        boundary_timestamp = pd.Timestamp(ordered.iloc[boundary_index]["session_open"])
    else:
        boundary_index = len(ordered) - 1
        boundary_timestamp = pd.Timestamp(
            ordered.iloc[-1]["session_open"]
        ) + pd.Timedelta(nanoseconds=1)
    if boundary_index <= start_index:
        raise Phase2MarketOnlyError(
            f"window has no evaluable path: {start_date}..{end_date}"
        )
    window = (
        ordered.iloc[start_index : boundary_index + 1].copy().reset_index(drop=True)
    )
    return window, pd.Timestamp(window.iloc[0]["session_open"]), boundary_timestamp


def _score_candidate_window(
    origins: pd.DataFrame,
    path: pd.DataFrame,
    candidate: dict[str, Any],
    cfg: dict[str, Any],
    costs: ExecutionCostAssumptions,
    risk: PaperRiskPolicy,
    *,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    window, start_timestamp, boundary_timestamp = _path_window(
        path, start_date=start_date, end_date=end_date
    )
    feature_columns = list(cfg["feature_sets"][candidate["feature_set"]])
    execution = cfg["execution_contract"]
    forecasts = forecast_candidate_window(
        origins,
        candidate,
        feature_columns,
        start_timestamp=start_timestamp,
        boundary_timestamp=boundary_timestamp,
        contract_multiplier=float(execution["contract_multiplier_mmbtu"]),
        min_train_rows=int(execution["minimum_training_rows"]),
        horizon_sessions=int(execution["horizon_sessions"]),
    )
    ledger, policy_summary = simulate_policy(
        window,
        forecasts,
        "forecast_sign",
        risk,
        costs,
        contract_multiplier=float(execution["contract_multiplier_mmbtu"]),
    )
    diagnostics = summarize_ledger(
        ledger,
        starting_capital_usd=risk.capital_usd,
    )
    diagnostics.update(_forecast_diagnostics(forecasts))
    score = {
        "candidate_id": str(candidate["id"]),
        "model": str(candidate["model"]),
        "feature_set": str(candidate["feature_set"]),
        "simplicity_rank": int(candidate.get("simplicity_rank", 999)),
        "start_date": start_date,
        "end_date": end_date,
        "start_timestamp": start_timestamp.isoformat(),
        "boundary_timestamp": boundary_timestamp.isoformat(),
        "training_rows": int(forecasts["training_rows"].iloc[0]),
        "latest_training_target_end": pd.Timestamp(
            forecasts["latest_training_target_end"].iloc[0]
        ).isoformat(),
        "net_pnl_usd": float(diagnostics["net_pnl_usd"]),
        "transaction_cost_usd": float(diagnostics["transaction_cost_usd"]),
        "max_drawdown_fraction": float(diagnostics["max_drawdown_fraction"]),
        "execution_side_count": int(diagnostics["execution_side_count"]),
        "kill_triggered": bool(policy_summary["kill_triggered"]),
        "diagnostics": diagnostics,
    }
    return score, forecasts, ledger


def _inner_fold_specs(cfg: dict[str, Any]) -> list[dict[str, str]]:
    validation = cfg["validation"]
    start = pd.Timestamp(validation["earliest_inner_validation_start"])
    latest_outer_start = max(
        pd.Timestamp(block["start"]) for block in validation["outer_blocks"]
    )
    months = int(validation["inner_validation_block_months"])
    if months < 1:
        raise Phase2MarketOnlyError("inner validation block length must be positive")
    folds: list[dict[str, str]] = []
    cursor = start
    while cursor < latest_outer_start:
        next_cursor = cursor + pd.DateOffset(months=months)
        end = min(
            next_cursor - pd.Timedelta(days=1),
            latest_outer_start - pd.Timedelta(days=1),
        )
        folds.append(
            {
                "id": f"inner-{cursor.date().isoformat()}-{end.date().isoformat()}",
                "start": cursor.date().isoformat(),
                "end": end.date().isoformat(),
            }
        )
        cursor = next_cursor
    return folds


def _safe_score_candidate(
    origins: pd.DataFrame,
    path: pd.DataFrame,
    candidate: dict[str, Any],
    cfg: dict[str, Any],
    costs: ExecutionCostAssumptions,
    risk: PaperRiskPolicy,
    block: dict[str, str],
) -> tuple[dict[str, Any], pd.DataFrame | None, pd.DataFrame | None]:
    try:
        score, forecasts, ledger = _score_candidate_window(
            origins,
            path,
            candidate,
            cfg,
            costs,
            risk,
            start_date=block["start"],
            end_date=block["end"],
        )
    except (Phase2MarketOnlyError, ValueError) as exc:
        return (
            {
                "candidate_id": str(candidate["id"]),
                "block_id": str(block["id"]),
                "status": "failed",
                "reason": str(exc),
                "simplicity_rank": int(candidate.get("simplicity_rank", 999)),
            },
            None,
            None,
        )
    score.update({"block_id": str(block["id"]), "status": "passed"})
    return score, forecasts, ledger


def _checkpointed_score_candidate(
    origins: pd.DataFrame,
    path: pd.DataFrame,
    candidate: dict[str, Any],
    cfg: dict[str, Any],
    costs: ExecutionCostAssumptions,
    risk: PaperRiskPolicy,
    block: dict[str, str],
    *,
    checkpoint_store: Phase2CheckpointStore | None,
    telemetry: Phase2Telemetry,
    cache_identity: dict[str, Any],
    cost_profile_id: str,
    require_frames: bool,
) -> tuple[dict[str, Any], pd.DataFrame | None, pd.DataFrame | None]:
    identity = {
        **cache_identity,
        "score_cache_version": 1,
        "block": block,
        "candidate": candidate,
        "cost_profile_id": cost_profile_id,
    }
    prefix = f"scores/{cost_profile_id}/{block['id']}/{candidate['id']}"
    if checkpoint_store is not None:
        cached_score = checkpoint_store.load_json(f"{prefix}-score", identity)
        if cached_score is not None:
            if cached_score.get("status") == "failed" or not require_frames:
                return cached_score, None, None
            cached_forecasts = checkpoint_store.load_frame(
                f"{prefix}-forecasts", identity
            )
            cached_ledger = checkpoint_store.load_frame(f"{prefix}-ledger", identity)
            if cached_forecasts is not None and cached_ledger is not None:
                return cached_score, cached_forecasts, cached_ledger
    with telemetry.stage(
        "candidate_score",
        block=str(block["id"]),
        candidate=str(candidate["id"]),
        cost_profile=cost_profile_id,
    ):
        score, forecasts, ledger = _safe_score_candidate(
            origins, path, candidate, cfg, costs, risk, block
        )
    if checkpoint_store is not None:
        checkpoint_store.save_json(f"{prefix}-score", score, identity)
        if require_frames and forecasts is not None and ledger is not None:
            checkpoint_store.save_frame(f"{prefix}-forecasts", forecasts, identity)
            checkpoint_store.save_frame(f"{prefix}-ledger", ledger, identity)
    return score, forecasts, ledger


def _aggregate_candidate_scores(
    scores: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    block_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        cid = str(candidate["id"])
        relevant = [
            row
            for row in scores
            if row.get("candidate_id") == cid and row.get("block_id") in block_ids
        ]
        if len(relevant) != len(block_ids) or any(
            row.get("status") != "passed" for row in relevant
        ):
            continue
        rows.append(
            {
                "candidate_id": cid,
                "net_pnl_usd": float(
                    sum(float(row["net_pnl_usd"]) for row in relevant)
                ),
                "transaction_cost_usd": float(
                    sum(float(row["transaction_cost_usd"]) for row in relevant)
                ),
                "simplicity_rank": int(candidate.get("simplicity_rank", 999)),
                "blocks": sorted(block_ids),
            }
        )
    return rows


def _load_inherited_risk_and_costs(
    cfg: dict[str, Any],
) -> tuple[PaperRiskPolicy, dict[str, ExecutionCostAssumptions]]:
    execution = cfg["execution_contract"]
    simulations = simulation_config()["decision_system_simulations"]
    simulation = simulations.get(execution["simulation_id"])
    if not isinstance(simulation, dict):
        raise Phase2MarketOnlyError("inherited Phase-1 simulation is unavailable")
    if int(simulation["horizon_sessions"]) != int(execution["horizon_sessions"]):
        raise Phase2MarketOnlyError(
            "Phase-2 horizon disagrees with the inherited simulation"
        )
    if float(simulation["contract_multiplier_mmbtu"]) != float(
        execution["contract_multiplier_mmbtu"]
    ):
        raise Phase2MarketOnlyError(
            "Phase-2 contract multiplier disagrees with Phase 1"
        )
    if str(simulation["roll_policy"]) != str(execution["roll_policy"]):
        raise Phase2MarketOnlyError("Phase-2 roll policy disagrees with Phase 1")
    policies = policy_config()["paper_risk_policies"]
    risk_payload = policies.get(execution["risk_policy_id"])
    if not isinstance(risk_payload, dict):
        raise Phase2MarketOnlyError(
            "inherited Phase-1 paper risk policy is unavailable"
        )
    risk = parse_risk_policy(risk_payload)
    expected_drawdown = float(
        cfg["selection"]["risk_engine_peak_drawdown_kill_fraction"]
    )
    if not math.isclose(risk.peak_drawdown_kill_fraction, expected_drawdown):
        raise Phase2MarketOnlyError(
            "Phase-2 drawdown kill disagrees with the inherited risk policy"
        )
    if risk.max_contracts != int(cfg["selection"]["constraint_max_contracts"]):
        raise Phase2MarketOnlyError(
            "Phase-2 exposure cap disagrees with the inherited risk policy"
        )
    costs = {
        name: parse_cost_assumptions(
            payload,
            tick_value_usd=float(execution["tick_value_usd"]),
        )
        for name, payload in cfg["cost_profiles"].items()
    }
    if "base" not in costs:
        raise Phase2MarketOnlyError("Phase-2 requires a base cost profile")
    return risk, costs


def _canonicalize_one_origin_per_fill(
    origins: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Collapse only equivalent duplicate fill origins to the latest PIT signal."""
    if origins.empty:
        return origins.copy(), {"input_origins": 0, "output_origins": 0, "collapsed": 0}
    frame = origins.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if frame[["signal_timestamp", "fill_timestamp", "target_end_timestamp"]].isna().any().any():
        raise Phase2MarketOnlyError("origin canonicalization found invalid timestamps")
    if (frame["signal_timestamp"] >= frame["fill_timestamp"]).any():
        raise Phase2MarketOnlyError("origin signal must strictly precede its executable fill")

    duplicate = frame[frame.duplicated("fill_timestamp", keep=False)].copy()
    if not duplicate.empty:
        for _, group in duplicate.groupby("fill_timestamp", sort=False):
            if group["fill_contract_id"].astype(str).nunique() != 1:
                raise Phase2MarketOnlyError("duplicate fill origins disagree on held contract")
            if group["target_end_timestamp"].nunique() != 1:
                raise Phase2MarketOnlyError("duplicate fill origins disagree on target end")
            target = pd.to_numeric(group["target_path_move_per_mmbtu"], errors="coerce")
            if target.isna().any() or not np.allclose(target.to_numpy(), target.iloc[0]):
                raise Phase2MarketOnlyError("duplicate fill origins disagree on target value")

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


def _build_segmented_decision_origins(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    *,
    horizon_sessions: int,
) -> tuple[pd.DataFrame, list[str]]:
    if "segment_id" not in session_path.columns:
        return build_decision_origins(
            session_path, features, horizon_sessions=horizon_sessions
        )
    feature_dates = pd.to_datetime(features["trade_date"], utc=True)
    parts: list[pd.DataFrame] = []
    feature_columns: list[str] | None = None
    for segment_id, segment in session_path.groupby("segment_id", sort=False):
        segment_dates = set(pd.to_datetime(segment["trade_date"], utc=True))
        segment_features = features.loc[feature_dates.isin(segment_dates)].copy()
        if segment_features.empty or len(segment) <= horizon_sessions:
            continue
        origins, columns = build_decision_origins(
            segment.reset_index(drop=True),
            segment_features.reset_index(drop=True),
            horizon_sessions=horizon_sessions,
        )
        if origins.empty:
            continue
        if feature_columns is None:
            feature_columns = columns
        elif feature_columns != columns:
            raise Phase2MarketOnlyError(
                "segmented origins produced inconsistent feature columns"
            )
        origins["segment_id"] = int(segment_id)
        parts.append(origins)
    if not parts or feature_columns is None:
        return pd.DataFrame(), []
    combined = (
        pd.concat(parts, ignore_index=True)
        .sort_values("signal_timestamp", kind="stable")
        .reset_index(drop=True)
    )
    return combined, feature_columns


def _preflight_evaluation_capacity(
    origins: pd.DataFrame,
    path: pd.DataFrame,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Prove structural fold/candidate viability before any model fitting."""
    execution = cfg["execution_contract"]
    min_train = int(execution["minimum_training_rows"])
    candidates = list(cfg["candidates"])
    blocks = [*_inner_fold_specs(cfg), *cfg["validation"]["outer_blocks"]]
    checks: list[dict[str, Any]] = []
    survivor_ids = {str(candidate["id"]) for candidate in candidates}

    for block in blocks:
        _, start_timestamp, boundary_timestamp = _path_window(
            path, start_date=block["start"], end_date=block["end"]
        )
        training = origins.loc[origins["target_end_timestamp"] < start_timestamp]
        evaluation = origins.loc[
            origins["fill_timestamp"].ge(start_timestamp)
            & origins["target_end_timestamp"].lt(boundary_timestamp)
        ]
        viable_ids: set[str] = set()
        for candidate in candidates:
            candidate_id = str(candidate["id"])
            columns = list(cfg["feature_sets"][candidate["feature_set"]])
            values = pd.concat([training[columns], evaluation[columns]], ignore_index=True)
            finite = bool(
                not values.empty
                and np.isfinite(values.to_numpy(dtype="float64")).all()
            )
            viable = len(training) >= min_train and not evaluation.empty and finite
            if viable:
                viable_ids.add(candidate_id)
            checks.append(
                {
                    "block_id": str(block["id"]),
                    "candidate_id": candidate_id,
                    "training_rows": len(training),
                    "evaluation_rows": len(evaluation),
                    "features_finite": finite,
                    "viable": viable,
                }
            )
        survivor_ids &= viable_ids
        if not survivor_ids:
            raise Phase2MarketOnlyError(
                f"preflight eliminated every candidate by block {block['id']}"
            )

    return {
        "blocks": len(blocks),
        "checks": len(checks),
        "structural_survivors": sorted(survivor_ids),
        "minimum_training_rows": min_train,
    }


def evaluate_phase2_market_only(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    checkpoint_store: Phase2CheckpointStore | None = None,
    telemetry: Phase2Telemetry | None = None,
    cache_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    telemetry = telemetry or Phase2Telemetry(None, echo=False)
    cache_identity = cache_identity or {"evaluation_cache_version": 1}
    validate_phase2_config(cfg)
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    execution = cfg["execution_contract"]
    origins, available_features = _build_segmented_decision_origins(
        session_path,
        features,
        horizon_sessions=int(execution["horizon_sessions"]),
    )
    if origins.empty:
        raise Phase2MarketOnlyError("Phase-2 target reconstruction produced no origins")
    origins, origin_canonicalization = _canonicalize_one_origin_per_fill(origins)
    telemetry.event(
        "evaluation_origins_ready",
        origins=len(origins),
        segments=int(origins["segment_id"].nunique()) if "segment_id" in origins else 1,
        **origin_canonicalization,
    )
    configured_features = {
        column for values in cfg["feature_sets"].values() for column in values
    }
    if not configured_features.issubset(available_features):
        missing = sorted(configured_features - set(available_features))
        raise Phase2MarketOnlyError(
            f"Phase-2 origins are missing configured features: {missing}"
        )

    preflight = _preflight_evaluation_capacity(origins, session_path, cfg)
    telemetry.event("evaluation_preflight_passed", **preflight)

    inner_folds = _inner_fold_specs(cfg)
    candidates = list(cfg["candidates"])
    inner_scores: list[dict[str, Any]] = []
    inner_survivors = {str(candidate["id"]) for candidate in candidates}
    for fold in inner_folds:
        fold_passed: set[str] = set()
        for candidate in candidates:
            score, _, _ = _checkpointed_score_candidate(
                origins,
                session_path,
                candidate,
                cfg,
                cost_profiles["base"],
                risk,
                fold,
                checkpoint_store=checkpoint_store,
                telemetry=telemetry,
                cache_identity=cache_identity,
                cost_profile_id="base",
                require_frames=False,
            )
            inner_scores.append(score)
            if score.get("status") == "passed":
                fold_passed.add(str(candidate["id"]))
        inner_survivors &= fold_passed
        telemetry.event(
            "inner_fold_survivors",
            block_id=str(fold["id"]),
            survivors=sorted(inner_survivors),
        )
        if not inner_survivors:
            raise Phase2MarketOnlyError(
                f"all candidates eliminated by required inner fold {fold['id']}"
            )
    outer_scores: list[dict[str, Any]] = []
    outer_ledgers: dict[tuple[str, str], pd.DataFrame] = {}
    outer_forecasts: dict[tuple[str, str], pd.DataFrame] = {}
    outer_survivors = {str(candidate["id"]) for candidate in candidates}
    for block in cfg["validation"]["outer_blocks"]:
        block_passed: set[str] = set()
        for candidate in candidates:
            score, forecasts, ledger = _checkpointed_score_candidate(
                origins,
                session_path,
                candidate,
                cfg,
                cost_profiles["base"],
                risk,
                block,
                checkpoint_store=checkpoint_store,
                telemetry=telemetry,
                cache_identity=cache_identity,
                cost_profile_id="base",
                require_frames=True,
            )
            outer_scores.append(score)
            if score.get("status") == "passed":
                block_passed.add(str(candidate["id"]))
            if forecasts is not None and ledger is not None:
                key = (str(block["id"]), str(candidate["id"]))
                outer_forecasts[key] = forecasts
                outer_ledgers[key] = ledger
        outer_survivors &= block_passed
        telemetry.event(
            "outer_block_survivors",
            block_id=str(block["id"]),
            survivors=sorted(outer_survivors),
        )
        if not outer_survivors:
            raise Phase2MarketOnlyError(
                f"all candidates eliminated by required outer block {block['id']}"
            )

    nested_outer: list[dict[str, Any]] = []
    for block in cfg["validation"]["outer_blocks"]:
        outer_start = pd.Timestamp(block["start"])
        eligible_ids = {
            fold["id"]
            for fold in inner_folds
            if pd.Timestamp(fold["end"]) < outer_start
        }
        aggregate = _aggregate_candidate_scores(inner_scores, candidates, eligible_ids)
        winner = select_best_candidate(aggregate)
        matching = [
            row
            for row in outer_scores
            if row.get("block_id") == block["id"]
            and row.get("candidate_id") == winner["candidate_id"]
            and row.get("status") == "passed"
        ]
        if len(matching) != 1:
            raise Phase2MarketOnlyError("nested winner lacks one valid outer score")
        nested_outer.append(
            {
                "block_id": block["id"],
                "selected_candidate_id": winner["candidate_id"],
                "inner_aggregate": winner,
                "outer_score": matching[0],
            }
        )

    outer_ids = {str(block["id"]) for block in cfg["validation"]["outer_blocks"]}
    final_aggregate = _aggregate_candidate_scores(outer_scores, candidates, outer_ids)
    final_winner = select_best_candidate(final_aggregate)
    winner_id = str(final_winner["candidate_id"])
    winner_candidate = _candidate_by_id(cfg, winner_id)
    winner_ledgers = [
        outer_ledgers[(str(block["id"]), winner_id)].assign(
            outer_block_id=str(block["id"])
        )
        for block in cfg["validation"]["outer_blocks"]
    ]
    winner_forecasts = [
        outer_forecasts[(str(block["id"]), winner_id)].assign(
            outer_block_id=str(block["id"])
        )
        for block in cfg["validation"]["outer_blocks"]
    ]
    combined_ledger = pd.concat(winner_ledgers, ignore_index=True)
    combined_forecasts = pd.concat(winner_forecasts, ignore_index=True)
    diagnostics = summarize_ledger(
        combined_ledger,
        starting_capital_usd=risk.capital_usd,
    )
    diagnostics["forecast"] = _forecast_diagnostics(combined_forecasts)
    combined_ledger["trade_date"] = pd.to_datetime(
        combined_ledger["trade_date"], utc=True
    )
    yearly = (
        combined_ledger.assign(year=combined_ledger["trade_date"].dt.year)
        .groupby("year", as_index=False)["net_pnl_usd"]
        .sum()
    )
    diagnostics["yearly_net_pnl_usd"] = {
        str(int(row.year)): float(row.net_pnl_usd)
        for row in yearly.itertuples(index=False)
    }
    abs_year = yearly["net_pnl_usd"].abs()
    diagnostics["largest_year_abs_pnl_fraction"] = (
        0.0 if float(abs_year.sum()) == 0.0 else float(abs_year.max() / abs_year.sum())
    )

    volatility = features[["trade_date", "feature_vol_20"]].copy()
    volatility["trade_date"] = pd.to_datetime(volatility["trade_date"], utc=True)
    q1, q2 = volatility["feature_vol_20"].quantile([1.0 / 3.0, 2.0 / 3.0]).tolist()
    if not math.isfinite(float(q1)) or not math.isfinite(float(q2)):
        raise Phase2MarketOnlyError("volatility-regime thresholds are invalid")
    volatility["volatility_regime"] = np.where(
        volatility["feature_vol_20"] <= q1,
        "low",
        np.where(volatility["feature_vol_20"] <= q2, "mid", "high"),
    )
    regime_ledger = combined_ledger.merge(
        volatility[["trade_date", "volatility_regime"]],
        on="trade_date",
        how="left",
        validate="many_to_one",
    )
    diagnostics["volatility_regime_thresholds"] = {
        "low_upper": float(q1),
        "mid_upper": float(q2),
    }
    diagnostics["volatility_regime_net_pnl_usd"] = {
        str(key): float(value)
        for key, value in regime_ledger.groupby("volatility_regime")["net_pnl_usd"]
        .sum()
        .items()
    }

    cost_sensitivity: list[dict[str, Any]] = []
    for profile_id, costs in cost_profiles.items():
        block_scores: list[dict[str, Any]] = []
        for block in cfg["validation"]["outer_blocks"]:
            if profile_id == "base":
                matches = [
                    row
                    for row in outer_scores
                    if row.get("block_id") == block["id"]
                    and row.get("candidate_id") == winner_id
                    and row.get("status") == "passed"
                ]
                if len(matches) != 1:
                    raise Phase2MarketOnlyError(
                        "base winner cost sensitivity score is missing"
                    )
                score = matches[0]
            else:
                score, _, _ = _checkpointed_score_candidate(
                    origins,
                    session_path,
                    winner_candidate,
                    cfg,
                    costs,
                    risk,
                    block,
                    checkpoint_store=checkpoint_store,
                    telemetry=telemetry,
                    cache_identity=cache_identity,
                    cost_profile_id=profile_id,
                    require_frames=False,
                )
                if score.get("status") != "passed":
                    raise Phase2MarketOnlyError(
                        f"winner failed cost sensitivity {profile_id}: {score.get('reason')}"
                    )
            block_scores.append(score)
        cost_sensitivity.append(
            {
                "profile_id": profile_id,
                "round_trip_cost_usd": float(costs.round_trip_usd),
                "net_pnl_usd": float(
                    sum(float(row["net_pnl_usd"]) for row in block_scores)
                ),
                "transaction_cost_usd": float(
                    sum(float(row["transaction_cost_usd"]) for row in block_scores)
                ),
                "blocks": [
                    {
                        "block_id": row["block_id"],
                        "net_pnl_usd": float(row["net_pnl_usd"]),
                    }
                    for row in block_scores
                ],
            }
        )

    nested_total = float(
        sum(float(item["outer_score"]["net_pnl_usd"]) for item in nested_outer)
    )
    return {
        "origins": len(origins),
        "origin_canonicalization": origin_canonicalization,
        "preflight": preflight,
        "inner_folds": inner_folds,
        "search_history": {
            "inner": inner_scores,
            "outer": outer_scores,
        },
        "nested_selection": {
            "outer_blocks": nested_outer,
            "cumulative_net_pnl_usd": nested_total,
        },
        "final_candidate_aggregate": final_aggregate,
        "final_baseline": {
            "candidate_id": winner_id,
            "candidate": winner_candidate,
            "outer_aggregate": final_winner,
            "feature_columns": list(
                cfg["feature_sets"][winner_candidate["feature_set"]]
            ),
        },
        "diagnostics": diagnostics,
        "cost_sensitivity": cost_sensitivity,
    }


def run_phase2_market_only(
    config_path: Path,
    databento_root: Path,
    *,
    checkpoint_dir: Path | None = None,
    heartbeat_seconds: float = 30.0,
) -> dict[str, Any]:
    config_bytes = Path(config_path).read_bytes()
    try:
        cfg = json.loads(config_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase2MarketOnlyError(f"invalid Phase-2 config: {exc}") from exc
    if not isinstance(cfg, dict):
        raise Phase2MarketOnlyError("Phase-2 config must be a JSON object")
    validate_phase2_config(cfg)
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    reconstruction_implementation_sha256 = _callable_bundle_sha256(
        [
            _archive_parts,
            _target_ohlcv,
            reconstruct_market_history,
            canonicalize_databento_dbn_partition,
            decode_databento_dbn_file,
            load_databento_definition_archive,
            map_databento_instrument_symbols,
            databento_contract_id,
            validate_contract_history,
        ]
    )
    input_implementation_sha256 = _callable_bundle_sha256(
        [
            _archive_parts,
            _target_ohlcv,
            _build_executable_selected_path,
            _validate_executable_selected,
            reconstruct_market_history,
            build_phase2_inputs,
            canonicalize_databento_dbn_partition,
            decode_databento_dbn_file,
            load_databento_definition_archive,
            map_databento_instrument_symbols,
            databento_contract_id,
            build_derived_continuous_series,
            build_market_structure_features,
            validate_contract_history,
            build_roll_safe_session_path,
        ]
    )
    evaluation_implementation_sha256 = _callable_bundle_sha256(
        [
            _build_segmented_decision_origins,
            _canonicalize_one_origin_per_fill,
            _preflight_evaluation_capacity,
            forecast_candidate_window,
            _score_candidate_window,
            _aggregate_candidate_scores,
            evaluate_phase2_market_only,
            HistGradientBoostingReturnModel,
            RidgeReturnModel,
            build_decision_origins,
            simulate_policy,
        ]
    )
    telemetry_path = None
    checkpoint_store = None
    if checkpoint_dir is not None:
        checkpoint_root = Path(checkpoint_dir)
        telemetry_path = checkpoint_root / "telemetry.jsonl"
        telemetry = Phase2Telemetry(
            telemetry_path,
            heartbeat_seconds=heartbeat_seconds,
            echo=True,
        )
        checkpoint_store = Phase2CheckpointStore(checkpoint_root, telemetry)
        lock_context = checkpoint_store.run_lock()
    else:
        telemetry = Phase2Telemetry(
            None, heartbeat_seconds=heartbeat_seconds, echo=True
        )
        lock_context = nullcontext()

    try:
        with lock_context:
            telemetry.event(
                "run_started",
                config_sha256=config_sha256,
                reconstruction_implementation_sha256=reconstruction_implementation_sha256,
                input_implementation_sha256=input_implementation_sha256,
                evaluation_implementation_sha256=evaluation_implementation_sha256,
                cutoff=str(cfg["evidence_boundary"]["last_allowed_trade_date"]),
                protected_confirmation_accessed=False,
            )
            reconstruction_store = checkpoint_store
            if checkpoint_store is not None:
                reconstruction_store = checkpoint_store.scoped_identity(
                    {
                        "reconstruction_implementation_sha256": reconstruction_implementation_sha256
                    },
                    allow_legacy_identity=(
                        reconstruction_implementation_sha256
                        == _LEGACY_RECONSTRUCTION_IMPLEMENTATION_SHA256
                    ),
                )
            canonical, market, execution_bars, provenance = reconstruct_market_history(
                databento_root,
                cfg,
                checkpoint_store=reconstruction_store,
                telemetry=telemetry,
            )
            legacy_input_cache_identity = {
                "input_cache_version": 5,
                "config_sha256": config_sha256,
                "source_provenance_sha256": provenance["provenance_sha256"],
            }
            input_cache_identity = {
                **legacy_input_cache_identity,
                "input_implementation_sha256": input_implementation_sha256,
            }
            session_path = None
            features = None
            legacy_input_reused = False
            if checkpoint_store is not None:
                session_path = checkpoint_store.load_frame(
                    "inputs/session-path", input_cache_identity
                )
                features = checkpoint_store.load_frame(
                    "inputs/features", input_cache_identity
                )
                if (
                    (session_path is None or features is None)
                    and input_implementation_sha256
                    == _LEGACY_INPUT_IMPLEMENTATION_SHA256
                ):
                    session_path = checkpoint_store.load_frame(
                        "inputs/session-path", legacy_input_cache_identity
                    )
                    features = checkpoint_store.load_frame(
                        "inputs/features", legacy_input_cache_identity
                    )
                    legacy_input_reused = session_path is not None and features is not None
            if session_path is None or features is None:
                with telemetry.stage("input_build"):
                    session_path, features = build_phase2_inputs(
                        canonical,
                        market,
                        execution_bars,
                        cfg,
                        telemetry=telemetry,
                    )
                if checkpoint_store is not None:
                    checkpoint_store.save_frame(
                        "inputs/session-path", session_path, input_cache_identity
                    )
                    checkpoint_store.save_frame(
                        "inputs/features", features, input_cache_identity
                    )
            cutoff = pd.Timestamp(
                cfg["evidence_boundary"]["last_allowed_trade_date"], tz="UTC"
            )
            path_dates = pd.to_datetime(session_path["trade_date"], utc=True)
            feature_dates = pd.to_datetime(features["trade_date"], utc=True)
            path_available = pd.to_datetime(session_path["available_at"], utc=True)
            path_opens = pd.to_datetime(session_path["session_open"], utc=True)
            if path_dates.max() > cutoff or feature_dates.max() > cutoff:
                raise Phase2MarketOnlyError(
                    "cached or rebuilt Phase-2 inputs crossed the protected cutoff"
                )
            if (path_available >= path_opens).any():
                raise Phase2MarketOnlyError(
                    "cached or rebuilt selected path crossed the strict executable information boundary"
                )
            lag_hours = (path_opens - path_available).dt.total_seconds() / 3600.0
            telemetry.event(
                "execution_timing_validated",
                rows=len(session_path),
                minimum_knowledge_lag_hours=float(lag_hours.min()),
                maximum_knowledge_lag_hours=float(lag_hours.max()),
            )
            if legacy_input_reused and checkpoint_store is not None:
                checkpoint_store.save_frame(
                    "inputs/session-path", session_path, input_cache_identity
                )
                checkpoint_store.save_frame(
                    "inputs/features", features, input_cache_identity
                )
                telemetry.event(
                    "legacy_input_checkpoint_upgraded",
                    input_implementation_sha256=input_implementation_sha256,
                )

            input_identity = {
                "session_path_sha256": _frame_sha256(session_path),
                "features_sha256": _frame_sha256(features),
                "source_provenance_sha256": provenance["provenance_sha256"],
                "input_implementation_sha256": input_implementation_sha256,
            }
            evaluation_cache_identity = {
                "evaluation_cache_version": 2,
                "evaluation_implementation_sha256": evaluation_implementation_sha256,
                "config_sha256": config_sha256,
                **input_identity,
            }
            evaluation = None
            if checkpoint_store is not None:
                evaluation = checkpoint_store.load_json(
                    "evaluation/result", evaluation_cache_identity
                )
            if evaluation is None:
                with telemetry.stage("nested_walk_forward_evaluation"):
                    evaluation = evaluate_phase2_market_only(
                        session_path,
                        features,
                        cfg,
                        checkpoint_store=checkpoint_store,
                        telemetry=telemetry,
                        cache_identity=evaluation_cache_identity,
                    )
                if checkpoint_store is not None:
                    checkpoint_store.save_json(
                        "evaluation/result", evaluation, evaluation_cache_identity
                    )
            freeze_payload = {
                "config_sha256": config_sha256,
                **input_identity,
                "candidate_id": evaluation["final_baseline"]["candidate_id"],
                "candidate": evaluation["final_baseline"]["candidate"],
                "feature_columns": evaluation["final_baseline"]["feature_columns"],
            }
            result = {
                "schema_version": 1,
                "programme_id": str(cfg["programme_id"]),
                "phase": int(cfg["phase"]),
                "authority": str(cfg["authority"]),
                "evidence_boundary": cfg["evidence_boundary"],
                "protected_confirmation_accessed": False,
                "source_provenance": provenance,
                "input_identity": input_identity,
                "phase2_config_sha256": config_sha256,
                "evaluation": evaluation,
                "baseline_freeze": {
                    **freeze_payload,
                    "freeze_sha256": _json_sha256(freeze_payload),
                    "evidence_role": "development_selected_market_only_baseline",
                    "confirmation_status": "not_confirmatory",
                },
                "claim_boundary": str(cfg["claim_boundary"]),
            }
            result["result_sha256"] = _json_sha256(result)
            telemetry.event(
                "run_completed",
                candidate_id=result["baseline_freeze"]["candidate_id"],
                result_sha256=result["result_sha256"],
            )
            return result
    except (Phase2RuntimeError, RuntimeError, ValueError, OSError) as exc:
        telemetry.event(
            "run_failed",
            detail=str(exc),
            error_type=type(exc).__name__,
        )
        if isinstance(exc, Phase2MarketOnlyError):
            raise
        raise Phase2MarketOnlyError(str(exc)) from exc
