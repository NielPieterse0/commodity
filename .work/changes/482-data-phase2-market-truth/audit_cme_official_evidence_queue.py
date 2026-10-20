"""Read-only per-contract CME verification queue from exact pre-2023 source bytes.

Never promotes source expiry to official truth or reads protected 2023+ outcomes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from audit_last_trade_metadata import MONTH_CODES, third_prior_weekday

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".work/runtime/market_truth_development/definitions-full-2010-2022.csv"
SOURCE_SHA256 = "dfd96778a31399c950425171c970ca1d0ccff6a933415a69412679499217fa23"
SOURCE_COLUMNS = (
    "instrument_id",
    "ts_event",
    "ts_recv",
    "asset",
    "instrument_class",
    "raw_symbol",
    "expiration",
    "exchange",
)
CME_NOTICE_CANDIDATES = {
    "2013-04": "https://www.cmegroup.com/tools-information/lookups/advisories/clearing/files/Chadv13-146.pdf",
    "2017-06": "https://www.cmegroup.com/notices/clearing/2017/04/Chadv17-144.pdf",
    "2021-06": "https://www.cmegroup.com/notices/clearing/2021/05/Chadv21-180R.pdf",
}


def build_queue(source: Path = SOURCE) -> dict:
    """Copy/hash once before parsing; originals are not modified."""
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("pinned source unavailable")
    # Windows keeps staging in the private repo runtime; locked offline Linux
    # uses its isolated temporary filesystem while /repo remains read-only.
    stage_root = source.parent if os.name == "nt" else None
    with tempfile.TemporaryDirectory(dir=stage_root, prefix=".cme-evidence-") as temp:
        staged = Path(temp) / "source.csv"
        digest = hashlib.sha256()
        total_bytes = 0
        with source.open("rb") as reader, staged.open("xb") as writer:
            for block in iter(lambda: reader.read(1 << 20), b""):
                total_bytes += len(block)
                if total_bytes > 128 * 1024 * 1024:
                    raise RuntimeError("source exceeds audited byte budget")
                digest.update(block)
                writer.write(block)
        if digest.hexdigest() != SOURCE_SHA256:
            raise RuntimeError("pinned source hash mismatch")
        with staged.open("r", encoding="utf-8-sig", newline="") as reader:
            records = csv.DictReader(reader, strict=True)
            if tuple(records.fieldnames or ()) != SOURCE_COLUMNS:
                raise RuntimeError("source definition schema drift")
            identities = set()
            for record in records:
                if not record["raw_symbol"] or not record["expiration"]:
                    raise RuntimeError("missing contract evidence")
                identities.add(
                    (record["exchange"], record["raw_symbol"], record["expiration"])
                )
    if len(identities) != 307:
        raise RuntimeError("contract cohort drift")
    cases = []
    for venue, symbol, expiration in sorted(identities):
        if venue != "XNYM":
            raise RuntimeError("source venue drift")
        match = re.fullmatch(r"NG([FGHJKMNQUVXZ])([0-9]{1,4})", symbol)
        if match is None:
            raise RuntimeError("unrecognized source contract")
        stamp = datetime.fromisoformat(expiration)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise RuntimeError("unqualified source timestamp")
        local = stamp.astimezone(ZoneInfo("America/New_York"))
        month = MONTH_CODES[match.group(1)]
        year = local.year + (month <= local.month)
        if year % 10 ** len(match.group(2)) != int(match.group(2)):
            raise RuntimeError("source symbol-year mismatch")
        if local.date() >= date(2023, 1, 1):
            continue
        proxy = third_prior_weekday(date(year, month, 1))
        if local.date() == proxy:
            continue
        delivery = f"{year}-{month:02d}"
        cases.append(
            {
                "source_exchange": venue,
                "source_symbol": symbol,
                "delivery_month": delivery,
                "source_expiration": expiration,
                "source_expiration_ny_date": local.date().isoformat(),
                "weekday_only_comparator_date": proxy.isoformat(),
                "source_minus_weekday_calendar_days": (local.date() - proxy).days,
                "official_CME_last_trade_verified": False,
                "notice_candidate_url": CME_NOTICE_CANDIDATES.get(delivery),
                "notice_candidate_status": "discovered_not_independently_qualified"
                if delivery in CME_NOTICE_CANDIDATES
                else "not_found",
                "research_use": "hold_expiry_dependent_decisions",
            }
        )
    if len(cases) != 14:
        raise RuntimeError("historical CME discrepancy count drift")
    return {
        "schema_version": 1,
        "issue": 482,
        "source_csv_sha256": SOURCE_SHA256,
        "source_unique_contracts": 307,
        "historical_weekday_comparator_discrepancies": len(cases),
        "basis": "pinned_original_provider_expiration_not_exchange_confirmation",
        "all_official_expiries_verified": False,
        "candidate_notices_are_unqualified": True,
        "dates_promoted": 0,
        "research_admission_approved": False,
        "protected_2023plus_accessed": False,
        "cases": cases,
    }


if __name__ == "__main__":
    print(json.dumps(build_queue(), indent=2, sort_keys=True))
