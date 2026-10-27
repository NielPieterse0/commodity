"""Bounded Databento / CME Henry Hub adapter. All broader logic is commodity-neutral."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from .core import (
    MarketTruthError,
    normalize_bars,
    normalize_definitions,
    normalize_statistics,
    parse_time,
)

NG_PRODUCT = "NG"
NG_VENUE = "NYMEX"
NG_TIMEZONE = "America/New_York"
NG_QUOTE_UNIT = "USD/MMBtu"
NG_CONTRACT_UNIT = "MMBtu"
NG_CONTRACT_SIZE = 10000
NG_TICK_SIZE = 0.001
LEGACY_SETTLEMENT_FLAG_END = date(2015, 11, 20)
PRELIMINARY_SETTLEMENT_FLAGS = frozenset({100, 101})
FINAL_SETTLEMENT_BIT = 1
INTRADAY_SETTLEMENT_BIT = 8


def databento_ng_settlement_eligible(row: dict[str, Any]) -> bool:
    """Interpret Databento settlement flags without rewriting source finality."""
    flags = int(row.get("stat_flags") or 0)
    if flags in PRELIMINARY_SETTLEMENT_FLAGS or flags & INTRADAY_SETTLEMENT_BIT:
        return False
    trade = date.fromisoformat(str(row["trade_date"]))
    if trade < LEGACY_SETTLEMENT_FLAG_END:
        return True  # Historic missing-final-bit candidates, not certified finals.
    return bool(flags & FINAL_SETTLEMENT_BIT) or row.get("is_final") in (True, 1, "true", "True", "1")


def normalize_ng_databento(
    definitions: list[dict[str, Any]],
    bars: list[dict[str, Any]],
    statistics: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep vendor clocks; map exact NG/CME identity without inferring unknown source values."""
    prepared_definitions = []
    for row in definitions:
        if (
            str(row.get("asset", "")).strip() != NG_PRODUCT
            or str(row.get("instrument_class", "")).strip() != "F"
        ):
            continue
        out = dict(row)
        venue = str(out.get("exchange", "")).strip()
        if venue not in {"XNYM", "NYMEX"}:
            raise MarketTruthError("unsupported NG venue")
        out["venue"] = NG_VENUE
        out["contract_size"] = NG_CONTRACT_SIZE
        out["quote_unit"] = NG_QUOTE_UNIT
        out["contract_unit"] = NG_CONTRACT_UNIT
        out["tick_size"] = NG_TICK_SIZE
        prepared_definitions.append(out)
    if not prepared_definitions:
        raise MarketTruthError("no outright NYMEX NG definitions")
    # Source files may contain other products. The provider adapter owns the
    # instrument universe; the generic core must never guess product scope.
    accepted = {str(row["instrument_id"]) for row in prepared_definitions}
    return (
        prepared_definitions,
        [dict(row) for row in bars if str(row.get("instrument_id")) in accepted],
        [
            dict(row)
            for row in statistics
            if str(row.get("instrument_id")) in accepted
        ],
    )



def normalize_ng_databento_record(
    family: str, raw: dict[str, str]
) -> dict[str, Any] | None:
    """Provider-owned streaming row mapping; generic writer knows no NG semantics."""
    if family == "definitions":
        if (
            str(raw.get("asset", "")).strip() != NG_PRODUCT
            or str(raw.get("instrument_class", "")).strip() != "F"
        ):
            return None
        prepared, _, _ = normalize_ng_databento([raw], [], [])
        rows = normalize_definitions(prepared)
    elif family == "bars":
        out = dict(raw)
        if not out.get("available_at"):
            try:
                day = date.fromisoformat(str(out["trade_date"]))
            except (KeyError, ValueError) as exc:
                raise MarketTruthError("trade_date required from decoded source") from exc
            out["available_at"] = datetime.combine(
                day, datetime.min.time(), tzinfo=UTC
            ).replace(hour=23, minute=59).isoformat()
        rows = normalize_bars([out])
    elif family == "statistics":
        out = dict(raw)
        if not out.get("trade_date"):
            if not out.get("ts_ref"):
                raise MarketTruthError("statistic trade_date/ts_ref missing")
            out["trade_date"] = str(out["ts_ref"])[:10]
        rows = normalize_statistics([out], settlement_policy=databento_ng_settlement_eligible)
    else:
        raise MarketTruthError("unsupported source family")
    if not rows:
        return None
    item = rows[0]
    if parse_time(item["event_at"]) > parse_time(item["available_at"]):
        raise MarketTruthError("source fact available before event timestamp")
    if item.get("source_vintage_id") is not None:
        item["source_vintage_id"] = str(item["source_vintage_id"])
    return item

def ng_curve_asof(
    store: dict[str, Any], session: date | str, decision_time: datetime | str,
    *, ranks: int = 12,
) -> list[dict[str, Any]]:
    """NG-specific eager selection with mandatory historical expiry fence."""
    from .core import curve_asof, parse_date
    from .ng_expiry import fence_ng_expiry_definitions, model_safe_ng_curve

    day = parse_date(session)
    cutoff = parse_time(decision_time)
    membership = min(
        cutoff, datetime.combine(day, datetime.max.time(), tzinfo=UTC)
    )
    checked = dict(store)
    checked["definitions"] = fence_ng_expiry_definitions(
        store["definitions"], membership
    )
    return model_safe_ng_curve(curve_asof(checked, day, cutoff, ranks=ranks))


def ng_snapshot_asof(
    store: dict[str, Any], session: date | str, decision_time: datetime | str,
    *, session_history=(),
) -> dict[str, Any]:
    """Source-owned V3 eager entry point; generic math stays NG-neutral."""
    from .core import snapshot_asof

    return snapshot_asof(
        store, session, decision_time, session_history=session_history,
        curve_lookup=lambda day, ranks: ng_curve_asof(
            store, day, decision_time, ranks=ranks
        ),
    )
