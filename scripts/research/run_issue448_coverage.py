from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import commodity.v2_optimization as v2
from commodity.cftc import parse_cftc_report_dates
from commodity.market_only_phase2 import (
    _inner_fold_specs,
    _load_inherited_risk_and_costs,
)
from commodity.providers import databento_futures as db
from commodity.v2_coverage import (
    Issue448CoverageError,
    build_issue448_market_structure_features,
    build_issue448_technical_features,
    evaluate_issue448_matched_candidate,
    evaluate_issue448_options_preflight,
    evaluate_issue448_storage_surprise_gate,
    issue448_family_outer_blocks,
    issue448_representation_selection_support,
    issue448_volatility_tail_handoff,
    load_issue448_contract,
    match_issue448_open_interest_to_contract_path,
    prepare_issue448_candidate_features,
    run_issue448_development_coverage,
    validate_issue448_selected_contract_ohlcv,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue448-prereg-v2.json"
SOURCE = PROGRAMME / "issue448-source-feasibility-v2.json"
RESULT = PROGRAMME / "issue448-result-v1.json"
PREFLIGHT = PROGRAMME / "issue448-preflight-v2.json"
LEDGER = PROGRAMME / "issue448-trials-v1.jsonl"
SOURCE_EVIDENCE = PROGRAMME / "issue448-source-pit-evidence-v1.json"
PHASE2 = REPO / "config/phase2_market_only.json"
ISSUE425 = PROGRAMME / "issue425-result-v1.json"
CACHE = REPO / "data/raw/issue448"
MAIN_REPO = REPO.parents[2] if REPO.parent.name == "worktrees" else REPO
DATABENTO = MAIN_REPO / "data/raw/snapshots/databento/ng-full-history-v1"
MARKET_CHECKPOINT = MAIN_REPO / ".work/worktrees/356-market-only-nested-walk-forward/.work/checkpoints/356-market-only-nested-walk-forward/inputs"
EXPECTED_FEATURE_SHA = "b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e"
EXPECTED_SESSION_SHA = "0fe87ea79a56f98fb9d445e89e3d65b48ae7bb1175e06ba9b97da68ebe6b01e8"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def annual_dbn(schema: str, year: int) -> Path:
    directory = DATABENTO / schema
    pattern = f"*{year}0101-{year}1231.{schema}.dbn.zst"
    matches = list(directory.rglob(pattern))
    if year == 2010 and not matches:
        matches = list(directory.rglob(f"*20100606-20101231.{schema}.dbn.zst"))
    if len(matches) != 1:
        raise RuntimeError(f"issue448 expected one {schema} DBN for {year}, found {len(matches)}")
    return matches[0]


def load_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_path = MARKET_CHECKPOINT / "features.parquet"
    session_path = MARKET_CHECKPOINT / "session-path.parquet"
    if sha256_file(feature_path) != EXPECTED_FEATURE_SHA:
        raise RuntimeError("issue448 frozen market feature identity changed")
    if sha256_file(session_path) != EXPECTED_SESSION_SHA:
        raise RuntimeError("issue448 frozen session identity changed")
    features = pd.read_parquet(feature_path)
    sessions = pd.read_parquet(session_path)
    cutoff = pd.Timestamp("2022-12-31", tz="UTC")
    if pd.to_datetime(features.trade_date, utc=True).max() > cutoff:
        raise RuntimeError("issue448 market features cross protected cutoff")
    if pd.to_datetime(sessions.trade_date, utc=True).max() > cutoff:
        raise RuntimeError("issue448 session path crosses protected cutoff")
    return features, sessions


def selected_contract_path(features: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    left = features[["trade_date", "available_at"]].copy()
    left["trade_date"] = pd.to_datetime(left.trade_date, utc=True)
    right = sessions[["trade_date", "contract_id"]].copy()
    right["trade_date"] = pd.to_datetime(right.trade_date, utc=True)
    out = left.merge(right, on="trade_date", how="left", validate="one_to_one")
    if out.contract_id.isna().any():
        raise RuntimeError("issue448 frozen feature row lacks selected contract")
    return out


def decode_year_sources(
    year: int,
    definitions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    definition_path = annual_dbn("definition", year)
    statistics_path = annual_dbn("statistics", year)
    ohlcv_path = annual_dbn("ohlcv-1d", year)
    annual_definitions, _ = db.decode_databento_dbn_file(
        definition_path, expected_schema="definition"
    )
    try:
        oi, oi_provenance = db.decode_databento_open_interest_contracts_dbn(
            definitions, statistics_path, product_code="NG"
        )
        oi_status = "valid_referenced_records"
        oi_accounting = dict(oi_provenance["open_interest_accounting"])
    except db.DatabentoOfflineDecodeError as exc:
        if "no valid referenced target contracts" not in str(exc):
            raise
        raw_oi, _ = db.decode_databento_open_interest_dbn(statistics_path)
        oi = pd.DataFrame(
            columns=["contract_id", "observed_for", "available_at", "open_interest"]
        )
        oi_status = "no_valid_referenced_records"
        oi_accounting = {
            "source_rows": len(raw_oi),
            "accepted_rows": 0,
            "rejected_rows": len(raw_oi),
            "reason": "no_valid_referenced_target_contracts",
        }
    bars, _ = db.decode_databento_dbn_file(ohlcv_path, expected_schema="ohlcv-1d")
    mappings = db._read_databento_dbn_symbol_mappings(
        ohlcv_path, expected_schema="ohlcv-1d", dataset=db.DATABENTO_DATASET
    )
    resolved = db.resolve_databento_metadata_symbols(bars, mappings)
    target_bars, bar_filter = db._filter_resolved_target_observations(
        definitions, resolved, product_code="NG", observation_kind="ohlcv"
    )
    mapped = db.map_databento_resolved_symbols_to_target_definitions(
        definitions, target_bars, product_code="NG"
    )
    daily = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(mapped["ts_event"], utc=True).dt.normalize(),
            "contract_id": db.databento_contract_id(
                mapped["symbol"], mapped["definition_expiration"]
            ),
            "high": pd.to_numeric(mapped["high"], errors="raise").astype(float),
            "low": pd.to_numeric(mapped["low"], errors="raise").astype(float),
            "close": pd.to_numeric(mapped["close"], errors="raise").astype(float),
            "volume": pd.to_numeric(mapped["volume"], errors="raise").astype(float),
        }
    )
    if daily.duplicated(["trade_date", "contract_id"]).any():
        raise RuntimeError(f"issue448 duplicate OHLCV contract/day in {year}")
    year_evidence = {
        "hashes": {
            "definition": sha256_file(definition_path),
            "statistics": sha256_file(statistics_path),
            "ohlcv_1d": sha256_file(ohlcv_path),
        },
        "open_interest_status": oi_status,
        "source_accounting": {
            "definition": {
                "accepted_rows": len(annual_definitions),
                "rejected_rows": 0,
                "reason": "decoded_into_global_definition_authority",
            },
            "statistics_open_interest": oi_accounting,
            "ohlcv_1d": {
                "accepted_rows": len(daily),
                "rejected_rows": len(bars) - len(daily),
                "reason_counts": {
                    "non_target_symbol": int(bar_filter["excluded_non_target_symbol"]),
                    "before_target_activation": int(
                        bar_filter["excluded_before_target_activation"]
                    ),
                },
            },
        },
    }
    return oi, daily, year_evidence


def build_databento_inputs(
    features: pd.DataFrame, sessions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    path = selected_contract_path(features, sessions)
    definition_paths = [annual_dbn("definition", year) for year in range(2010, 2023)]
    definitions, definition_authority = db.load_databento_definition_archive(
        definition_paths, product_code="NG"
    )
    oi_parts: list[pd.DataFrame] = []
    bar_parts: list[pd.DataFrame] = []
    evidence: dict[str, object] = {
        "definition_authority_sha256": str(
            definition_authority["definition_authority_sha256"]
        ),
        "years": {},
    }
    years = evidence["years"]
    assert isinstance(years, dict)
    for year in range(2010, 2023):
        print(f"issue448 source-build year={year}", flush=True)
        oi, bars, year_evidence = decode_year_sources(year, definitions)
        oi_parts.append(oi)
        bar_parts.append(bars)
        years[str(year)] = year_evidence
    publications = pd.concat(oi_parts, ignore_index=True).sort_values(
        ["available_at", "contract_id", "observed_for"], kind="stable"
    )
    matched_oi = match_issue448_open_interest_to_contract_path(path, publications)
    bars = pd.concat(bar_parts, ignore_index=True)
    selected_bars = validate_issue448_selected_contract_ohlcv(path, bars)
    required = ["high", "low", "close", "volume"]
    technical_market = path[["trade_date", "available_at"]].merge(
        selected_bars[["trade_date", *required]],
        on="trade_date",
        how="left",
        validate="one_to_one",
    )
    technical_market["settle"] = np.exp(
        pd.to_numeric(features["feature_curve_log_settle_m1"], errors="raise").to_numpy()
    )
    CACHE.mkdir(parents=True, exist_ok=True)
    matched_oi.to_parquet(CACHE / "selected-oi.parquet", index=False)
    technical_market.to_parquet(CACHE / "selected-technical-market.parquet", index=False)
    evidence["selected_open_interest_rows"] = len(matched_oi)
    evidence["selected_technical_market_rows"] = len(technical_market)
    return matched_oi, technical_market, evidence


def cftc_archive_frame(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [
            item for item in archive.infolist()
            if not item.is_dir() and Path(item.filename).suffix.lower() in {".txt", ".csv"}
        ]
        if len(members) != 1:
            raise RuntimeError("issue448 CFTC archive member identity is ambiguous")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, dtype=str, low_memory=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def historical_cftc_available_at(report_date: pd.Timestamp) -> tuple[pd.Timestamp, str]:
    day = pd.Timestamp(report_date).date()
    basis = "cftc_report_date_plus_7d_conservative"
    publication_day = day + dt.timedelta(days=7)
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


def load_cftc_positioning() -> tuple[pd.DataFrame, dict[str, object]]:
    cache_dir = CACHE / "cftc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    parts: list[pd.DataFrame] = []
    evidence: dict[str, object] = {"years": {}}
    years = evidence["years"]
    assert isinstance(years, dict)
    session = requests.Session()
    for year in range(2010, 2023):
        path = cache_dir / f"fut_disagg_txt_{year}.zip"
        url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
        if not path.exists():
            response = session.get(url, timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
        content = path.read_bytes()
        archive_sha256 = hashlib.sha256(content).hexdigest()
        raw = cftc_archive_frame(content)
        codes = raw["CFTC_Contract_Market_Code"].astype(str).str.strip().str.zfill(6)
        frame = raw.loc[codes.eq("023651")].copy()
        frame = frame.loc[frame["FutOnly_or_Combined"].astype(str).str.strip().eq("FutOnly")]
        report_date = parse_cftc_report_dates(frame)
        availability = [historical_cftc_available_at(value) for value in report_date]
        numeric = {
            name: pd.to_numeric(frame[name], errors="raise").astype(float)
            for name in (
                "Open_Interest_All",
                "M_Money_Positions_Long_All",
                "M_Money_Positions_Short_All",
                "Prod_Merc_Positions_Long_All",
                "Prod_Merc_Positions_Short_All",
            )
        }
        rows = pd.DataFrame(
            {
                "observed_for": report_date,
                "available_at": [item[0] for item in availability],
                "availability_basis": [item[1] for item in availability],
                "open_interest": numeric["Open_Interest_All"],
                "managed_money_net": numeric["M_Money_Positions_Long_All"]
                - numeric["M_Money_Positions_Short_All"],
                "producer_merchant_net": numeric["Prod_Merc_Positions_Long_All"]
                - numeric["Prod_Merc_Positions_Short_All"],
            }
        )
        years[str(year)] = {
            "sha256": archive_sha256,
            "accepted_rows": len(rows),
            "rejected_rows": len(raw) - len(rows),
            "reason": "non_target_market_or_non_futures_only",
        }
        parts.append(rows)
    out = pd.concat(parts, ignore_index=True).sort_values(
        ["available_at", "observed_for"], kind="stable"
    )
    before_publication_collapse = len(out)
    out = out.drop_duplicates("available_at", keep="last")
    evidence["collapsed_conservative_publication_rows"] = (
        before_publication_collapse - len(out)
    )
    if (out["available_at"] <= out["observed_for"]).any():
        raise RuntimeError("issue448 CFTC availability precedes report observation")
    return out.reset_index(drop=True), evidence


def curve_frame(features: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.to_datetime(features.trade_date, utc=True),
            "available_at": pd.to_datetime(features.available_at, utc=True),
            "log_settle_m1": features.feature_curve_log_settle_m1,
            "log_settle_m2": features.feature_curve_log_settle_m2,
            "log_settle_m3": features.feature_curve_log_settle_m3,
            "log_settle_m4": features.feature_curve_log_settle_m4,
            "dte_m1": features.feature_curve_dte_m1,
            "dte_m2": features.feature_curve_dte_m2,
            "dte_m4": features.feature_curve_dte_m4,
            "volume_m1": np.exp(features.feature_curve_log_volume_m1),
        }
    )


def assemble_features(
    contract: object,
    market: pd.DataFrame,
    sessions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]], dict[str, object]]:
    selected_oi, technical_market, databento_evidence = build_databento_inputs(market, sessions)
    positioning, cftc_evidence = load_cftc_positioning()
    technical, technical_families = build_issue448_technical_features(technical_market, contract)
    structure, structure_families = build_issue448_market_structure_features(
        curve_frame(market), selected_oi, positioning, contract
    )
    merged = market.copy()
    for extra in (technical, structure):
        value_columns = [c for c in extra.columns if c not in {"trade_date", "available_at"}]
        merged = merged.merge(
            extra[["trade_date", "available_at", *value_columns]],
            on=["trade_date", "available_at"],
            how="left",
            validate="one_to_one",
        )
    families = {**technical_families, **structure_families}
    evidence = {
        "databento": databento_evidence,
        "cftc": cftc_evidence,
        "selected_oi_rows": len(selected_oi),
        "selected_oi_populated_rows": int(selected_oi.open_interest_m1.notna().sum()),
        "technical_market_rows": len(technical_market),
        "cftc_report_rows": len(positioning),
        "event_timing_status": "HOLD_NO_PROVEN_HISTORICAL_WNGSR_RELEASE_CALENDAR",
    }
    return merged, families, evidence


def options_preflight(contract: object) -> tuple[dict[str, object], list[str]]:
    option_metadata = json.loads(
        (DATABENTO / "definition/GLBX-20260813-4LWDSMFX5T/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    local_symbols = sorted(set(map(str, option_metadata.get("query", {}).get("symbols", []))))
    option_inventory = bool({"ON.OPT", "LNE.OPT"} & set(local_symbols))
    result = evaluate_issue448_options_preflight(
        {
            "local_inventory": option_inventory,
            "metadata_schema_compatible": True,
            "quoted_cost_usd": None,
            "private_research_licensing_permission": True,
            "strike_expiry_depth_verified": False,
            "pit_timestamp_semantics_verified": False,
        },
        contract,
    )
    return result, local_symbols


def _block_row_counts(
    prepared: pd.DataFrame, blocks: Sequence[Mapping[str, str]]
) -> dict[str, int]:
    trade_date = pd.to_datetime(prepared["trade_date"], utc=True)
    counts: dict[str, int] = {}
    for block in blocks:
        start = pd.Timestamp(str(block["start"]), tz="UTC")
        end = pd.Timestamp(str(block["end"]), tz="UTC")
        counts[str(block["id"])] = int(trade_date.between(start, end).sum())
    return counts


def _candidate_preflight(
    merged: pd.DataFrame,
    sessions: pd.DataFrame,
    families: Mapping[str, Sequence[str]],
    cfg: Mapping[str, object],
    outer_controls: Mapping[str, Mapping[str, object]],
    costs: object,
    minimum_training_rows: int,
    family_outer_blocks: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> tuple[dict[str, object], dict[str, object], list[str]]:
    inner_blocks = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    family_outer_blocks = family_outer_blocks or {}
    proofs: dict[str, object] = {}
    selection_support: dict[str, object] = {}
    scorable_outers: dict[str, set[str]] = {str(family): set() for family in families}
    failures: list[str] = []

    for family, representations in families.items():
        active_outers = family_outer_blocks.get(str(family), outer_blocks)
        for outer in active_outers:
            outer_id = str(outer["id"])
            control_outer_id = str(outer.get("parent_control_outer_id", outer_id))
            if control_outer_id not in outer_controls:
                failures.append(f"{outer_id}:{family}:missing_parent_control={control_outer_id}")
                continue
            config = dict(outer_controls[control_outer_id]["config"])
            outer_start = pd.Timestamp(str(outer["start"]), tz="UTC")
            prior_inner = [
                block
                for block in inner_blocks
                if pd.Timestamp(str(block["end"]), tz="UTC") < outer_start
            ]
            declared_selection_ids = outer.get("selection_inner_block_ids")
            if declared_selection_ids is not None:
                declared_ids = [str(value) for value in declared_selection_ids]
                prior_by_id = {str(block["id"]): block for block in prior_inner}
                if len(declared_ids) != len(set(declared_ids)) or not set(declared_ids).issubset(
                    prior_by_id
                ):
                    failures.append(f"{outer_id}:{family}:invalid_preregistered_selection_blocks")
                    continue
                prior_inner = [block for block in prior_inner if str(block["id"]) in set(declared_ids)]
            required_blocks = [*prior_inner, outer]
            support = issue448_representation_selection_support(
                sessions,
                merged,
                config=config,
                representations=representations,
                inner_blocks=prior_inner,
                outer_block=outer,
                phase2_cfg=cfg,
                costs=costs,
                minimum_training_rows=minimum_training_rows,
            )
            selection_support.setdefault(outer_id, {})[str(family)] = support
            if support["available_representations"] and support["common_selection_block_ids"]:
                scorable_outers[str(family)].add(outer_id)
            if declared_selection_ids is not None and support["common_selection_block_ids"] != [
                str(value) for value in declared_selection_ids
            ]:
                failures.append(f"{outer_id}:{family}:selection_support_mismatches_preregistration")

            family_proof: dict[str, object] = {}
            for representation in representations:
                try:
                    prepared, candidate_columns, control_columns = (
                        prepare_issue448_candidate_features(
                            merged, config, str(representation)
                        )
                    )
                    candidate_complete = prepared[candidate_columns].notna().all(axis=1)
                    control_complete = prepared[control_columns].notna().all(axis=1)
                    identical = bool(
                        candidate_complete.equals(control_complete)
                        and candidate_complete.all()
                    )
                    counts = _block_row_counts(prepared, required_blocks)
                    if not identical:
                        failures.append(
                            f"{outer_id}:{family}:{representation}:candidate_control_rows_differ"
                        )
                    row_identity = stable_sha(
                        [value.isoformat() for value in pd.to_datetime(prepared["trade_date"], utc=True)]
                    )
                    family_proof[str(representation)] = {
                        "prepared_rows": len(prepared),
                        "row_identity_sha256": row_identity,
                        "candidate_control_rows_identical": identical,
                        "candidate_feature_columns": candidate_columns,
                        "control_feature_column_count": len(control_columns),
                        "block_complete_rows": counts,
                        "parent_control_outer_id": control_outer_id,
                    }
                except (Issue448CoverageError, KeyError, TypeError, ValueError) as exc:
                    failures.append(
                        f"{outer_id}:{family}:{representation}:preflight_error={exc}"
                    )
            proofs.setdefault(outer_id, {})[str(family)] = family_proof

    for family, outer_ids in sorted(scorable_outers.items()):
        if not outer_ids:
            failures.append(f"{family}:no_scorable_outer_support")
    return proofs, selection_support, failures


def preflight_coverage() -> dict[str, object]:
    contract = load_issue448_contract(PREREG, SOURCE)
    market, sessions = load_market()
    merged, families, source_evidence = assemble_features(contract, market, sessions)
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    _risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    outer_controls = v2.load_issue426_outer_matched_controls(ISSUE425)
    family_outer_blocks = issue448_family_outer_blocks(contract)
    proofs, selection_support, failures = _candidate_preflight(
        merged,
        sessions,
        families,
        cfg,
        outer_controls,
        costs,
        minimum_training_rows,
        family_outer_blocks=family_outer_blocks,
    )
    cutoff = pd.Timestamp("2022-12-31", tz="UTC")
    trade_dates = pd.to_datetime(merged["trade_date"], utc=True)
    max_trade_date = trade_dates.max()
    if max_trade_date > cutoff:
        failures.append(f"feature_matrix_crosses_cutoff:{max_trade_date.isoformat()}")
    if len(merged) != len(market):
        failures.append(
            f"feature_matrix_row_count_changed:market={len(market)} merged={len(merged)}"
        )
    options, local_symbols = options_preflight(contract)
    storage = evaluate_issue448_storage_surprise_gate(None, contract)
    CACHE.mkdir(parents=True, exist_ok=True)
    feature_cache = CACHE / "preflight-features.parquet"
    family_cache = CACHE / "preflight-families.json"
    merged.to_parquet(feature_cache, index=False)
    family_cache.write_text(
        json.dumps(
            {name: list(columns) for name, columns in families.items()},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 448,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "development_cutoff": "2022-12-31",
        "feature_rows": len(merged),
        "max_trade_date": max_trade_date.isoformat(),
        "family_count": len(families),
        "candidate_control_row_proofs": proofs,
        "candidate_selection_support": selection_support,
        "failures": failures,
        "source_pit_evidence": source_evidence,
        "event_timing": {
            "disposition": "HOLD",
            "reason": "no proven historical 2010-2022 WNGSR release calendar",
        },
        "storage_consensus_surprise": storage,
        "options_implied": options,
        "databento_local_definition_parent_symbols": local_symbols,
        "cache": {
            "features_sha256": sha256_file(feature_cache),
            "families_sha256": sha256_file(family_cache),
        },
        "market_features_sha256": EXPECTED_FEATURE_SHA,
        "session_path_sha256": EXPECTED_SESSION_SHA,
        "code_sha256": sha256_file(REPO / "src/commodity/v2_coverage.py"),
        "provider_code_sha256": sha256_file(
            REPO / "src/commodity/providers/databento_futures.py"
        ),
        "cftc_code_sha256": sha256_file(REPO / "src/commodity/cftc.py"),
        "authority_sha256": {
            "prereg": sha256_file(PREREG),
            "source_feasibility": sha256_file(SOURCE),
            "phase2_market_only": sha256_file(PHASE2),
            "issue425_result": sha256_file(ISSUE425),
        },
        "runner_sha256": sha256_file(Path(__file__)),
    }
    report["preflight_sha256"] = stable_sha(
        {key: value for key, value in report.items() if key != "preflight_sha256"}
    )
    PREFLIGHT.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    SOURCE_EVIDENCE.write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def load_preflight_cache() -> tuple[
    pd.DataFrame,
    dict[str, tuple[str, ...]],
    dict[str, object],
    dict[str, object],
]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue448 scoring requires a completed preflight report")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise RuntimeError("issue448 scoring blocked because preflight did not pass")
    expected_hashes = {
        "code_sha256": sha256_file(REPO / "src/commodity/v2_coverage.py"),
        "provider_code_sha256": sha256_file(
            REPO / "src/commodity/providers/databento_futures.py"
        ),
        "cftc_code_sha256": sha256_file(REPO / "src/commodity/cftc.py"),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    for key, value in expected_hashes.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue448 preflight is stale: {key} changed")
    authority = report.get("authority_sha256", {})
    if not isinstance(authority, Mapping):
        raise TypeError("issue448 preflight authority hashes are missing")
    current_authority = {
        "prereg": sha256_file(PREREG),
        "source_feasibility": sha256_file(SOURCE),
        "phase2_market_only": sha256_file(PHASE2),
        "issue425_result": sha256_file(ISSUE425),
    }
    if dict(authority) != current_authority:
        raise RuntimeError("issue448 preflight is stale: authority identity changed")
    feature_cache = CACHE / "preflight-features.parquet"
    family_cache = CACHE / "preflight-families.json"
    cache = report.get("cache", {})
    if not isinstance(cache, Mapping):
        raise TypeError("issue448 preflight cache identity is missing")
    if sha256_file(feature_cache) != cache.get("features_sha256"):
        raise RuntimeError("issue448 preflight feature cache hash changed")
    if sha256_file(family_cache) != cache.get("families_sha256"):
        raise RuntimeError("issue448 preflight family cache hash changed")
    merged = pd.read_parquet(feature_cache)
    raw_families = json.loads(family_cache.read_text(encoding="utf-8"))
    families = {name: tuple(columns) for name, columns in raw_families.items()}
    source_evidence = report.get("source_pit_evidence", {})
    if not isinstance(source_evidence, dict):
        raise TypeError("issue448 preflight source evidence is invalid")
    selection_support = report.get("candidate_selection_support", {})
    if not isinstance(selection_support, dict):
        raise TypeError("issue448 preflight selection support is invalid")
    return merged, families, source_evidence, selection_support


def score_coverage() -> dict[str, object]:
    contract = load_issue448_contract(PREREG, SOURCE)
    _market, sessions = load_market()
    merged, families, source_evidence, selection_support = load_preflight_cache()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    inner_blocks = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    outer_controls = v2.load_issue426_outer_matched_controls(ISSUE425)
    family_outer_blocks = issue448_family_outer_blocks(contract)
    parent_control_outer_ids = {
        str(block["id"]): str(block["parent_control_outer_id"])
        for blocks in family_outer_blocks.values()
        for block in blocks
    }

    def evaluator(
        stage: str,
        outer_id: str,
        blocks: Sequence[Mapping[str, str]],
        family: str,
        representation: str,
    ) -> dict[str, object]:
        control_outer_id = parent_control_outer_ids.get(outer_id, outer_id)
        if control_outer_id not in outer_controls:
            raise RuntimeError(
                f"issue448 missing #425 matched control for {outer_id}:parent={control_outer_id}"
            )
        result = evaluate_issue448_matched_candidate(
            session_path=sessions,
            features=merged,
            config=dict(outer_controls[control_outer_id]["config"]),
            candidate_column=representation,
            blocks=blocks,
            phase2_cfg=cfg,
            risk=risk,
            costs=costs,
            minimum_training_rows=minimum_training_rows,
        )
        return result

    def selection_supporter(
        outer: Mapping[str, str],
        family: str,
        representations: Sequence[str],
        prior_inner: Sequence[Mapping[str, str]],
    ) -> dict[str, object]:
        outer_id = str(outer["id"])
        outer_support = selection_support.get(outer_id)
        if not isinstance(outer_support, Mapping):
            raise TypeError(f"issue448 preflight lacks selection support for {outer_id}")
        support = outer_support.get(family)
        if not isinstance(support, Mapping):
            raise TypeError(
                f"issue448 preflight lacks selection support for {outer_id}:{family}"
            )
        known_prior = {str(block["id"]) for block in prior_inner}
        common_ids = [str(value) for value in support.get("common_selection_block_ids", [])]
        if not set(common_ids).issubset(known_prior):
            raise RuntimeError(
                f"issue448 preflight selection support crossed chronology for {outer_id}:{family}"
            )
        declared = set(map(str, representations))
        available = set(map(str, support.get("available_representations", [])))
        held = set(map(str, support.get("held_representations", [])))
        if not available.issubset(declared) or not held.issubset(declared):
            raise RuntimeError(
                f"issue448 preflight selection support changed candidates for {outer_id}:{family}"
            )
        return dict(support)

    held_families = {
        "event_timing": "HOLD_NO_PROVEN_HISTORICAL_WNGSR_RELEASE_CALENDAR",
        "storage_consensus_surprise": "HOLD_SOURCE_NOT_PROVEN",
        "options_implied": "HOLD_ZERO_SPEND_ACTIVATION_NOT_PROVEN",
        "volatility_tail_specialists": "DOWNSTREAM_ONLY_427_428_430",
    }
    scorable_families = {
        name: tuple(columns)
        for name, columns in families.items()
        if name != "event_timing"
    }
    result = run_issue448_development_coverage(
        contract=contract,
        family_candidates=scorable_families,
        held_families=held_families,
        inner_blocks=inner_blocks,
        outer_blocks=outer_blocks,
        evaluator=evaluator,
        selection_supporter=selection_supporter,
        family_outer_blocks=family_outer_blocks,
    )
    options, local_symbols = options_preflight(contract)
    option_inventory = bool({"ON.OPT", "LNE.OPT"} & set(local_symbols))
    storage = evaluate_issue448_storage_surprise_gate(None, contract)
    volatility_handoff = issue448_volatility_tail_handoff(contract)
    source_evidence.update(
        {
            "market_features_sha256": EXPECTED_FEATURE_SHA,
            "session_path_sha256": EXPECTED_SESSION_SHA,
            "databento_local_definition_parent_symbols": sorted(local_symbols),
            "options_local_inventory_found": option_inventory,
            "event_timing_disposition": held_families["event_timing"],
        }
    )
    downstream_handoff = {
        "schema_version": 1,
        "issue": 448,
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "consumers": [427, 428, 430],
        "retained_families": sorted(
            name
            for name, item in result["family_results"].items()
            if isinstance(item, Mapping)
            and str(item.get("disposition", "")).startswith("RETAIN_")
        ),
        "conditional_role_candidates": sorted(
            name
            for name, item in result["family_results"].items()
            if isinstance(item, Mapping)
            and str(item.get("disposition", "")).startswith("HOLD_NO_MATCHED")
        ),
        "storage_consensus_surprise": storage,
        "options_implied": options,
        "volatility_tail": volatility_handoff,
        "event_timing": {
            "disposition": held_families["event_timing"],
            "revisit_trigger": "complete authoritative 2010-2022 WNGSR holiday/exception release registry",
        },
    }
    result["source_pit_evidence"] = source_evidence
    result["storage_consensus_surprise"] = storage
    result["options_implied"] = options
    result["volatility_tail_handoff"] = volatility_handoff
    result["downstream_handoff"] = downstream_handoff
    result["code_sha256"] = sha256_file(REPO / "src/commodity/v2_coverage.py")
    result["runner_sha256"] = sha256_file(Path(__file__))

    LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in result["trials"]),
        encoding="utf-8",
        newline="\n",
    )
    SOURCE_EVIDENCE.write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    handoff_path = PROGRAMME / "issue448-downstream-handoff-v1.json"
    handoff_path.write_text(
        json.dumps(downstream_handoff, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result["trial_ledger_file_sha256"] = sha256_file(LEDGER)
    result["source_pit_evidence_file_sha256"] = sha256_file(SOURCE_EVIDENCE)
    result["downstream_handoff_file_sha256"] = sha256_file(handoff_path)
    result["result_sha256"] = stable_sha({k: v for k, v in result.items() if k != "result_sha256"})
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--preflight"
    if mode == "--preflight":
        report = preflight_coverage()
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scoring_performed": report["scoring_performed"],
                    "feature_rows": report["feature_rows"],
                    "failures": report["failures"],
                    "preflight_sha256": report["preflight_sha256"],
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        if report["status"] != "PASS":
            raise SystemExit(2)
        return
    if mode != "--score":
        raise SystemExit("usage: run_issue448_coverage.py [--preflight|--score]")

    result = score_coverage()
    summary = {
        "trial_count": result["trial_count"],
        "retained": {
            name: item.get("mean_monthly_net_return_delta")
            for name, item in result["family_results"].items()
            if isinstance(item, Mapping)
            and str(item.get("disposition", "")).startswith("RETAIN_")
        },
        "held": {
            name: item.get("disposition")
            for name, item in result["family_results"].items()
            if isinstance(item, Mapping)
            and not str(item.get("disposition", "")).startswith("RETAIN_")
        },
        "result_sha256": result["result_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
