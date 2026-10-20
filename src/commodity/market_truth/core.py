"""Append-only market facts and decision-time historical futures curve snapshots.

Core accepts source observations only; venue/product details belong to adapters.
No file discovery, provider access or protected-research namespace access occurs here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from .errors import MarketTruthError
from .revision import REVISION_GRAINS, canonicalize_versions

SCHEMA_VERSION = 1
MAX_DEVELOPMENT_DATE = date(2022, 12, 31)



def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min, tzinfo=UTC)
    elif isinstance(value, str) and value.strip():
        try:
            result = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise MarketTruthError("invalid temporal timestamp") from exc
    else:
        raise MarketTruthError("timestamp missing or unsupported")
    if result.tzinfo is None or result.utcoffset() is None:
        raise MarketTruthError("timezone-naive timestamp prohibited")
    return result.astimezone(UTC)


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return parse_time(value).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise MarketTruthError("invalid session date") from exc


def assert_development_date(value: date) -> None:
    if value > MAX_DEVELOPMENT_DATE:
        raise MarketTruthError(
            "protected_confirmation_boundary: development date exceeds 2022"
        )


def _required(row: dict[str, Any], *names: str) -> None:
    missing = [key for key in names if row.get(key) is None or row.get(key) == ""]
    if missing:
        raise MarketTruthError("missing source evidence: " + ",".join(missing))


def _timestamp(row: dict[str, Any], *names: str) -> datetime:
    for key in names:
        if row.get(key) is not None and row.get(key) != "":
            return parse_time(row[key])
    raise MarketTruthError("unknown source publication/availability time")


def _numeric(value: Any, name: str, *, nonnegative: bool = False) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise MarketTruthError(f"invalid numeric {name}") from exc
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise MarketTruthError(f"invalid numeric {name}")
    return number


def _identity(row: dict[str, Any]) -> str:
    _required(row, "instrument_id")
    result = str(row["instrument_id"])
    if not result or result in {"nan", "None"}:
        raise MarketTruthError("invalid instrument identity")
    return result


def _evidence(row: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _source_available(row: dict[str, Any]) -> datetime:
    """Conservative, causal bound for inconsistent source/receive clocks.

    Keep explicit availability authoritative. Without it, a record cannot
    become visible before either its source event or capture receive clock.
    """
    if row.get("available_at") not in (None, ""):
        return parse_time(row["available_at"])
    received = _timestamp(row, "ts_recv", "ts_event")
    event = _timestamp(row, "ts_event", "ts_recv")
    return max(received, event)


def normalize_definitions(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        _required(row, "raw_symbol", "expiration", "venue")
        assert_development_date(_timestamp(row, "ts_event", "available_at").date())
        available = _source_available(row)
        assert_development_date(available.date())
        expiry = parse_time(row["expiration"])
        if expiry.date() < date(2000, 1, 1):
            raise MarketTruthError("invalid contract expiration")
        source_id = _identity(row)
        item = {
            "instrument_id": source_id,
            "venue": str(row["venue"]),
            "symbol": str(row["raw_symbol"]).strip(),
            "expiration": expiry.isoformat(),
            "available_at": available.isoformat(),
            "event_at": _timestamp(row, "ts_event", "available_at").isoformat(),
            "last_trade_at": (
                parse_time(row["last_trade_at"]).isoformat()
                if row.get("last_trade_at")
                else None
            ),
            "contract_size": row.get("contract_size"),
            "quote_unit": row.get("quote_unit"),
            "tick_size": row.get("tick_size"),
            "source_vintage_id": row.get("source_vintage_id"),
            "evidence_id": _evidence(row),
        }
        if not item["symbol"]:
            raise MarketTruthError("empty raw contract symbol")
        result.append(item)
    return canonicalize_versions(result, REVISION_GRAINS["definitions"], "definition")


def normalize_bars(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        _required(row, "trade_date", "open", "high", "low", "close", "volume")
        trade = parse_date(row["trade_date"])
        assert_development_date(trade)
        # Vendor daily record timestamps do not, alone, prove historical publication.
        available = _timestamp(row, "available_at")
        assert_development_date(available.date())
        prices = {
            key: _numeric(row[key], key) for key in ("open", "high", "low", "close")
        }
        if prices["high"] < max(prices["open"], prices["close"], prices["low"]):
            raise MarketTruthError("OHLC high inconsistent")
        if prices["low"] > min(prices["open"], prices["close"], prices["high"]):
            raise MarketTruthError("OHLC low inconsistent")
        volume = _numeric(row["volume"], "volume", nonnegative=True)
        if volume != int(volume):
            raise MarketTruthError("fractional contract volume")
        result.append(
            {
                "instrument_id": _identity(row),
                "trade_date": trade.isoformat(),
                "available_at": available.isoformat(),
                "event_at": _timestamp(row, "ts_event", "available_at").isoformat(),
                "source_vintage_id": row.get("source_vintage_id"),
                **prices,
                "volume": int(volume),
                "evidence_id": _evidence(row),
            }
        )
    return canonicalize_versions(result, REVISION_GRAINS["bars"], "bar")


def normalize_statistics(
    rows: Iterable[dict[str, Any]],
    *,
    settlement_policy: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    result = []
    stat_types = {3: "settle", 6: "cleared_volume", 9: "open_interest"}
    for row in rows:
        _required(row, "trade_date", "stat_type")
        trade = parse_date(row["trade_date"])
        assert_development_date(trade)
        available = _source_available(row)
        assert_development_date(available.date())
        try:
            stat_type = int(row["stat_type"])
        except (TypeError, ValueError) as exc:
            raise MarketTruthError("invalid statistics type") from exc
        if stat_type not in stat_types:
            continue
        finality = row.get("is_final")
        if stat_type == 3:
            if isinstance(finality, str):
                normalized = finality.strip().lower()
                if normalized in {"true", "1"}:
                    finality = True
                elif normalized in {"false", "0"}:
                    finality = False
                elif normalized == "":
                    finality = None
                else:
                    raise MarketTruthError("invalid settlement finality assertion")
            elif type(finality) is int and finality in {0, 1}:
                finality = bool(finality)
            elif finality is not None and type(finality) is not bool:
                raise MarketTruthError("invalid settlement finality assertion")
        # Provider-specific historical flag semantics are injected by adapters.
        # Without a provider policy the safe default requires affirmative finality.
        if stat_type == 3 and (
            finality is False
            or not (
                settlement_policy(row)
                if settlement_policy is not None
                else finality is True
            )
        ):
            continue
        name = stat_types[stat_type]
        value = _numeric(
            row.get("price") if name == "settle" else row.get("quantity"),
            name,
            nonnegative=name != "settle",
        )
        result.append(
            {
                "instrument_id": _identity(row),
                "trade_date": trade.isoformat(),
                "available_at": available.isoformat(),
                "event_at": _timestamp(row, "ts_event", "available_at").isoformat(),
                "stat_type": name,
                "value": value,
                "source_vintage_id": row.get("source_vintage_id"),
                "evidence_id": _evidence(row),
            }
        )
    return canonicalize_versions(result, REVISION_GRAINS["statistics"], "statistic")


def build_market_truth(
    definitions: list[dict[str, Any]],
    bars: list[dict[str, Any]],
    statistics: list[dict[str, Any]],
    *,
    source_hashes: dict[str, str] | None = None,
    settlement_policy: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Natural-grain append-only fact store; cannot read filesystem or provider."""
    if not definitions or not bars:
        raise MarketTruthError("market truth requires definitions and OHLCV")
    dimension = normalize_definitions(definitions)
    prices = normalize_bars(bars)
    stats = normalize_statistics(statistics, settlement_policy=settlement_policy)
    known = {row["instrument_id"] for row in dimension}
    for family in (dimension, prices, stats):
        for row in family:
            if parse_time(row["event_at"]) > parse_time(row["available_at"]):
                raise MarketTruthError("source fact available before event timestamp")
            if row["instrument_id"] not in known:
                raise MarketTruthError(
                    "market fact has no verified source contract identity"
                )
    return {
        "schema_version": SCHEMA_VERSION,
        "definitions": dimension,
        "bars": prices,
        "statistics": stats,
        "source_sha256": dict(sorted((source_hashes or {}).items())),
        "protected_confirmation_accessed": False,
    }


def _latest(
    rows: Iterable[dict[str, Any]], key: tuple[str, ...], cutoff: datetime
) -> dict[tuple[Any, ...], dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        ts = parse_time(row["available_at"])
        if ts > cutoff:
            continue
        token = tuple(row[k] for k in key)
        previous = selected.get(token)
        if previous is None or parse_time(previous["available_at"]) < ts:
            selected[token] = row
    return selected


def curve_asof(
    store: dict[str, Any],
    session: date | str,
    decision_time: datetime | str,
    *,
    ranks: int = 12,
) -> list[dict[str, Any]]:
    """Build M1–M12 using only definitions and facts observable at T."""
    session_day = parse_date(session)
    assert_development_date(session_day)
    cutoff = parse_time(decision_time)
    assert_development_date(cutoff.date())
    if session_day > cutoff.date():
        raise MarketTruthError("session is later than decision time")
    if ranks < 1 or ranks > 12:
        raise MarketTruthError("curve ranks must be within 1..12")
    session_end = datetime.combine(session_day, time(23, 59, 59, 999999), tzinfo=UTC)
    membership_cutoff = min(cutoff, session_end)
    definitions = _latest(
        store["definitions"], ("venue", "instrument_id"), membership_cutoff
    )
    # Historical contract ranks may not depend on definitions first seen in later sessions.
    contracts: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in definitions.values():
        last = parse_time(entry["last_trade_at"] or entry["expiration"])
        # A contract that stopped trading earlier in this session is not an
        # eligible curve rank at a later decision cutoff that same day.
        if last <= membership_cutoff:
            continue
        identity = (entry["venue"], entry["symbol"])
        existing = contracts.get(identity)
        if existing is not None and (
            existing["instrument_id"] != entry["instrument_id"]
            or existing["expiration"] != entry["expiration"]
        ):
            raise MarketTruthError("ambiguous source contract alias mapping")
        contracts[identity] = entry
    selected = sorted(
        contracts.values(),
        key=lambda r: (
            parse_time(r["expiration"]),
            r["venue"],
            r["symbol"],
            r["instrument_id"],
        ),
    )[:ranks]
    session_key = session_day.isoformat()
    bars = _latest(
        (r for r in store["bars"] if r["trade_date"] == session_key),
        ("instrument_id", "trade_date"),
        cutoff,
    )
    stats = _latest(
        (r for r in store["statistics"] if r["trade_date"] == session_key),
        ("instrument_id", "trade_date", "stat_type"),
        cutoff,
    )
    output = []
    for rank in range(1, ranks + 1):
        info = selected[rank - 1] if rank <= len(selected) else None
        instrument_id = info["instrument_id"] if info else None
        bar = bars.get((instrument_id, session_key)) if instrument_id else None
        values = {
            name: stats.get((instrument_id, session_key, name))
            if instrument_id
            else None
            for name in ("settle", "open_interest", "cleared_volume")
        }
        settle = values["settle"]
        fields = {
            "trade_date": session_key,
            "rank": rank,
            "instrument_id": instrument_id,
            "venue": info["venue"] if info else None,
            "contract_identity": (
                f"{info['venue']}:{info['symbol']}:{info['expiration']}"
                if info
                else None
            ),
            "contract_symbol": info["symbol"] if info else None,
            "expiration": info["expiration"] if info else None,
            "last_trade_at": info["last_trade_at"] if info else None,
            "last_trade_verified": bool(
                info and info["last_trade_at"] and not info.get("_expiry_unverified")
            ),
            "rank_boundary_status": (
                "unverified_exchange_expiry"
                if info and info.get("_expiry_unverified")
                else "verified_last_trade"
                if info and info["last_trade_at"]
                else "expiry_fallback_unverified"
                if info
                else "not_listed"
            ),
            "days_to_expiry": (
                (parse_time(info["expiration"]).date() - session_day).days
                if info and not info.get("_expiry_unverified")
                else None
            ),
            "open": bar["open"] if bar else None,
            "high": bar["high"] if bar else None,
            "low": bar["low"] if bar else None,
            "close": bar["close"] if bar else None,
            "volume": bar["volume"] if bar else None,
            "settle": settle["value"] if settle else None,
            "open_interest": values["open_interest"]["value"]
            if values["open_interest"]
            else None,
            "cleared_volume": values["cleared_volume"]["value"]
            if values["cleared_volume"]
            else None,
            "missing_reason": (
                "no_listed_contract"
                if not info
                else "source_missing_price"
                if not settle and not bar
                else "none"
            ),
            "available_at": max(
                [x["available_at"] for x in [info, bar, *values.values()] if x],
                default=None,
            ),
            "evidence_ids": sorted(
                {x["evidence_id"] for x in [info, bar, *values.values()] if x}
            ),
        }
        output.append(fields)
    return output


def _price(point: dict[str, Any]) -> float | None:
    value = point["settle"] if point["settle"] is not None else point["close"]
    return float(value) if value is not None else None


def snapshot_asof(
    store: dict[str, Any],
    session: date | str,
    decision_time: datetime | str,
    *,
    session_history: Iterable[date | str] = (),
    curve_lookup: Callable[[date, int], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Sparse V3 contract with causal price/curve and same-contract momentum."""
    def lookup(day: date, count: int) -> list[dict[str, Any]]:
        if curve_lookup is not None:
            return curve_lookup(day, count)
        return curve_asof(store, day, decision_time, ranks=count)

    curve = lookup(parse_date(session), 12)
    current = curve[0]
    first = _price(current)
    second = _price(curve[1])
    third = _price(curve[2])
    history: list[tuple[str, float | None]] = []
    previous_front: dict[str, Any] | None = None
    prior_sessions = sorted(
        day
        for day in {parse_date(x) for x in session_history}
        if day < parse_date(session)
    )
    for candidate in prior_sessions:
        point = lookup(candidate, 1)[0]
        previous_front = point
        # Preserve missing observations and roll transitions in the declared
        # session sequence; never compress a 20-session horizon into older dates.
        past = (
            _price(point)
            if current["contract_identity"] is not None
            and point["contract_identity"] == current["contract_identity"]
            and point["instrument_id"] == current["instrument_id"]
            else None
        )
        history.append((candidate.isoformat(), past))

    def pct_return(lag: int) -> float | None:
        if first is None or len(history) < lag:
            return None
        window = history[-lag:]
        if any(value is None for _, value in window):
            return None
        previous = window[0][1]
        return first / previous - 1 if previous else None

    spread = first - second if first is not None and second is not None else None
    curve_slope = (
        (third - first) / 2 if first is not None and third is not None else None
    )
    curvature = (
        first - 2 * second + third
        if first is not None and second is not None and third is not None
        else None
    )
    unqualified_rank = any(
        row["rank_boundary_status"] in {
            "unverified_exchange_expiry", "unverified_exchange_expiry_rank"
        }
        for row in curve
    )
    valid_prices = [value for row in curve if (value := _price(row)) is not None]
    level = (
        sum(valid_prices) / len(valid_prices)
        if valid_prices and not unqualified_rank
        else None
    )
    months = [
        (parse_time(row["expiration"]).month, value)
        for row in curve
        if row["expiration"] and (value := _price(row)) is not None
    ]
    winter = [value for month, value in months if month in {11, 12, 1, 2, 3}]
    summer = [value for month, value in months if month in {4, 5, 6, 7, 8, 9, 10}]
    winter_summer = (
        sum(winter) / len(winter) - sum(summer) / len(summer)
        if len(winter) >= 2 and len(summer) >= 2 and not unqualified_rank
        else None
    )
    calendar_days = (
        (parse_time(curve[1]["expiration"]) - parse_time(curve[0]["expiration"])).days
        if (curve[0]["expiration"] and curve[1]["expiration"]
            and curve[0]["days_to_expiry"] is not None
            and curve[1]["days_to_expiry"] is not None)
        else 0
    )
    annualized_carry = (
        (second - first) / abs(first) * 365.0 / calendar_days
        if first is not None and second is not None and first != 0 and calendar_days > 0
        else None
    )
    earlier = [value for _, value in history]
    volatility = None
    maximum_jump = None
    if first is not None and len(earlier) >= 20:
        values = [*earlier[-20:], first]
        if all(number is not None and number > 0 for number in values):
            returns = [
                math.log(values[i] / values[i - 1]) for i in range(1, len(values))
            ]
            mean = sum(returns) / len(returns)
            volatility = math.sqrt(
                sum((number - mean) ** 2 for number in returns) / (len(returns) - 1)
            ) * math.sqrt(252)
            maximum_jump = max(abs(number) for number in returns)
    rolled = (
        previous_front["contract_identity"] != current["contract_identity"]
        if previous_front is not None
        and previous_front["contract_identity"] is not None
        and current["contract_identity"] is not None
        and previous_front["rank_boundary_status"] != "unverified_exchange_expiry"
        and current["rank_boundary_status"] != "unverified_exchange_expiry"
        else None
    )
    liquidity = (
        current["volume"] / current["open_interest"]
        if current["volume"] is not None
        and current["open_interest"] is not None
        and current["open_interest"] > 0
        else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_time": parse_time(decision_time).isoformat(),
        "trade_date": parse_date(session).isoformat(),
        "protected_confirmation_accessed": False,
        "session_history_contract": "caller_supplied_complete_session_calendar",
        "curve_points": curve,
        "roll_transition": {
            "observed": rolled,
            "previous_session": (
                prior_sessions[-1].isoformat() if prior_sessions else None
            ),
            "previous_contract": (
                previous_front["contract_symbol"] if previous_front else None
            ),
            "current_contract": current["contract_symbol"],
        },
        "features": {
            "front_price": first,
            "m1_m2_spread_price_per_unit": spread,
            "m1_m3_slope_per_rank": curve_slope,
            "m1_m2_m3_curvature": curvature,
            "curve_mean_price_per_unit": level,
            "available_curve_slots": len(valid_prices),
            "winter_minus_summer_strip": winter_summer,
            "winter_strip_contracts": len(winter) if not unqualified_rank else None,
            "summer_strip_contracts": len(summer) if not unqualified_rank else None,
            "m1_m2_annualized_carry_proxy": annualized_carry,
            "front_liquidity_volume_oi_ratio": liquidity,
            "front_realized_volatility_20_annualized": volatility,
            "front_max_abs_log_return_20": maximum_jump,
            "session_month": parse_date(session).month,
            "session_weekday": parse_date(session).weekday(),
            "front_days_to_expiry": current["days_to_expiry"],
            "front_volume": current["volume"],
            "front_open_interest": current["open_interest"],
            "front_momentum_1": pct_return(1),
            "front_momentum_5": pct_return(5),
            "front_momentum_20": pct_return(20),
        },
        "feature_warmup": {
            "front_momentum_1": 1,
            "front_momentum_5": 5,
            "front_momentum_20": 20,
            "front_realized_volatility_20_annualized": 20,
            "front_max_abs_log_return_20": 20,
            "winter_minus_summer_strip": "at_least_2_observed_contracts_per_strip",
        },
        "feature_units": {
            "front_price": "quoted_price_per_unit",
            "m1_m2_spread_price_per_unit": "quoted_price_per_unit",
            "m1_m3_slope_per_rank": "quoted_price_per_unit_per_rank",
            "m1_m2_m3_curvature": "quoted_price_per_unit",
            "winter_minus_summer_strip": "quoted_price_per_unit",
            "m1_m2_annualized_carry_proxy": "fraction_per_calendar_year",
            "front_realized_volatility_20_annualized": "annualized_fraction",
        },
        "evidence_ids": sorted({item for row in curve for item in row["evidence_ids"]}),
        "source_sha256": store.get("source_sha256", {}),
    }


def publish_parquet(
    store: dict[str, Any],
    output_dir: Path,
    *,
    source_manifest_sha256: str | None = None,
    source_counts: dict[str, int] | None = None,
    config_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atomically publish a new immutable zstd dataset with reproducible hashes."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise MarketTruthError(
            "Parquet publishing requires pinned pyarrow runtime"
        ) from exc
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise MarketTruthError("refusing overwrite of existing dataset output")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".market-truth-build-", dir=output_dir.parent))
    try:
        tables = {}
        for family in ("definitions", "bars", "statistics"):
            path = stage / (family + ".parquet")
            pq.write_table(
                pa.Table.from_pylist(store[family]),
                path,
                compression="zstd",
                use_dictionary=True,
            )
            digest = hashlib.sha256()
            with path.open("rb") as data:
                for chunk in iter(lambda: data.read(1024 * 1024), b""):
                    digest.update(chunk)
            tables[family] = {
                "relative_path": path.name,
                "sha256": digest.hexdigest(),
                "rows": len(store[family]),
                "bytes": path.stat().st_size,
                "compression": "zstd",
            }
        module_files = ("core.py", "ng.py", "query.py", "protected_reads.py", "revision.py", "errors.py")
        transform_sha256 = {
            name: hashlib.sha256(
                (Path(__file__).parent / name).read_bytes()
            ).hexdigest()
            for name in module_files
        }
        raw_counts = dict(sorted((source_counts or {}).items()))
        if source_counts is not None and set(raw_counts) != {
            "definitions",
            "bars",
            "statistics",
        }:
            raise MarketTruthError("incomplete source count audit")
        normalized_counts = {name: table["rows"] for name, table in tables.items()}
        if raw_counts and any(
            raw_counts[name] < normalized_counts[name] for name in raw_counts
        ):
            raise MarketTruthError(
                "source-to-Parquet materialization exceeds input counts"
            )
        source_row_reconciliation = {
            name: {
                "source_rows": raw_counts[name],
                "normalized_rows": normalized_counts[name],
                "excluded_or_exact_retransmissions": (
                    raw_counts[name] - normalized_counts[name]
                ),
            }
            for name in raw_counts
        }
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "dataset_scope": "development_pre2023",
            "protected_confirmation_accessed": False,
            "source_sha256": store.get("source_sha256", {}),
            "transform_sha256": transform_sha256,
            "config_sha256": dict(sorted((config_sha256 or {}).items())),
            "source_row_reconciliation": source_row_reconciliation,
            "tables": tables,
        }
        if source_manifest_sha256 is not None:
            if len(source_manifest_sha256) != 64:
                raise MarketTruthError("invalid source manifest hash")
            metadata["source_manifest_sha256"] = source_manifest_sha256
        metadata["content_sha256"] = _evidence(metadata)
        (stage / "manifest.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(stage, output_dir)
        return metadata
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
