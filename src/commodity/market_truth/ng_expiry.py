"""NG-only fail-closed policy for 14 unqualified historical CME expiry boundaries.

The dates are source-identity pins, NOT independently qualified exchange times.
Price and volume bytes remain intact; unsafe rank decisions must not be emitted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from .core import MarketTruthError, parse_time

# (symbol, exact original expiration timestamp); symbols repeat across decades.
UNQUALIFIED_NG_EXPIRIES = frozenset({
    ("NGZ0", "2010-11-24T19:30:00+00:00"),
    ("NGF1", "2010-12-28T19:30:00+00:00"),
    ("NGM1", "2011-05-26T18:30:00+00:00"),
    ("NGJ3", "2013-03-26T18:30:00+00:00"),
    ("NGZ3", "2013-11-26T19:30:00+00:00"),
    ("NGZ4", "2014-11-25T19:30:00+00:00"),
    ("NGZ5", "2015-11-25T19:30:00+00:00"),
    ("NGM6", "2016-05-26T18:30:00+00:00"),
    ("NGM7", "2017-05-26T18:30:00+00:00"),
    ("NGJ8", "2018-03-27T18:30:00+00:00"),
    ("NGZ9", "2019-11-26T19:30:00+00:00"),
    ("NGZ0", "2020-11-25T19:30:00+00:00"),
    ("NGM1", "2021-05-26T18:30:00+00:00"),
    ("NGM2", "2022-05-26T18:30:00+00:00"),
})

# Contract delivery-month boundary for the pinned 14-case NG cohort.
# NYMEX Rule 220102.F forbids trading after the third business day before
# delivery month. A date at or after its first day is beyond that absolute
# eligibility boundary, even when historical expiry hours are unverified.
# https://www.cmegroup.com/rulebook/NYMEX/2/220.pdf
# Historical CME filing (2012):
# https://www.cftc.gov/sites/default/files/stellent/groups/public/@rulesandproducts/documents/ifdocs/rul111412nymex001.pdf
NG_DELIVERY_MONTH_CODES = "FGHJKMNQUVXZ"


def ng_delivery_month_start(symbol: str, expiration: str) -> date:
    """Bind delivery month/year and a <=7-day gap to an exact cohort tuple.

    This is not exchange-issued historical intraday expiry confirmation.
    Incompatible symbol, date or delivery distance is denied, not guessed.
    """
    try:
        if (symbol, expiration) not in UNQUALIFIED_NG_EXPIRIES:
            raise ValueError("contract is not in the release-pinned CME cohort")
        source_day = parse_time(expiration).date()
        if (
            len(symbol) != 4 or not symbol.startswith("NG")
            or symbol[2] not in NG_DELIVERY_MONTH_CODES
            or not symbol[3].isdigit()
        ):
            raise ValueError("unqualified CME contract has invalid delivery symbol")
        # Derive delivery month from the exact source contract symbol, then
        # independently require the source expiry to lie in its prior month.
        month = NG_DELIVERY_MONTH_CODES.index(symbol[2]) + 1
        year = source_day.year + (month <= source_day.month)
        delivery = date(year, month, 1)
        if (
            month != source_day.month % 12 + 1
            or symbol[3] != str(year % 10)
            or not 0 < (delivery - source_day).days <= 7
        ):
            raise ValueError("unqualified CME contract outside delivery bound")
        return delivery
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        raise MarketTruthError(
            "unverified CME delivery-month bound; research use denied"
        ) from exc


# Hash-pinned independently recorded cohort: cme-expiry-exposure-receipt.json.
# A deployment must not accept a shortened, removed or silently altered fence.
NG_EXPIRY_COHORT_SHA256 = (
    "a6c11d1fc824bca35745f2cfb4cd7d87849da4310ffc661a0d0fbe568cb26ffd"
)


def verify_ng_expiry_policy() -> None:
    """Fail closed on an absent or mutated 14-contract release-owned exclusion."""
    try:
        identities = sorted(
            ("NYMEX", symbol, expiration)
            for symbol, expiration in UNQUALIFIED_NG_EXPIRIES
        )
        actual = sha256(json.dumps(
            identities, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        if len(identities) != 14 or actual != NG_EXPIRY_COHORT_SHA256:
            raise ValueError("unexpected CME exclusion cohort")
        for _venue, symbol, expiration in identities:
            ng_delivery_month_start(symbol, expiration)
    except (TypeError, ValueError, KeyError) as exc:
        raise MarketTruthError(
            "CME expiry exclusion policy missing or modified; research use denied"
        ) from exc


def fence_ng_expiry_definitions(
    definitions: Iterable[dict[str, Any]], membership_cutoff: datetime,
) -> list[dict[str, Any]]:
    """Annotate known unverified expiries and deny terminal-window curve ranks.

    The seven-day quarantine either side remains a conservative source
    exclusion, not an asserted historical exchange expiration. All 14
    release-pinned source expiries are proven at most seven calendar days
    before their matching symbol's delivery month, and NYMEX Rule 220102.F
    terminates trade strictly before that month. Beyond the quarantine
    an already source-expired contract cannot lawfully re-enter the curve.
    No unsupported expiry time is promoted as an observed fact.
    """
    verify_ng_expiry_policy()
    cutoff = parse_time(membership_cutoff)
    result = []
    for entry in definitions:
        row = dict(entry)
        if row.get("available_at") and parse_time(row["available_at"]) > cutoff:
            result.append(row)
            continue
        expiry = parse_time(row["expiration"])
        identity = (row["symbol"], expiry.isoformat())
        if row["venue"] == "NYMEX" and identity in UNQUALIFIED_NG_EXPIRIES:
            delivery_start = ng_delivery_month_start(*identity)
            # The known historical termination may occur after the recorded
            # source expiry, but CME Chapter 220 prohibits trading after the
            # delivery month begins. Do not silently prune in that interval.
            if (
                abs((cutoff.date() - expiry.date()).days) <= 7
                or expiry <= cutoff and cutoff.date() < delivery_start
            ):
                raise MarketTruthError(
                    "unverified CME historical expiry decision window; "
                    "no market-truth curve selection permitted"
                )
            row["_expiry_unverified"] = True
        result.append(row)
    return result


def model_safe_ng_curve(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Withhold uncertain rank suffixes from V3 while retaining raw source facts.

    Once a selected contract has unqualified expiry membership, its rank and
    all following ranks can shift. Their contract identities and observations
    remain accessible only through source-layer queries, not model snapshots.
    """
    tainted = False
    safe = []
    for point in curve:
        if point["rank_boundary_status"] == "unverified_exchange_expiry":
            tainted = True
        if not tainted:
            safe.append(point)
            continue
        masked = dict(point)
        for name in (
            "instrument_id", "venue", "contract_identity", "contract_symbol",
            "expiration", "last_trade_at", "days_to_expiry", "open", "high",
            "low", "close", "volume", "settle", "open_interest",
            "cleared_volume", "available_at",
        ):
            masked[name] = None
        masked["last_trade_verified"] = False
        masked["rank_boundary_status"] = "unverified_exchange_expiry_rank"
        masked["missing_reason"] = "unverified_exchange_expiry_rank"
        masked["evidence_ids"] = []
        safe.append(masked)
    return safe
