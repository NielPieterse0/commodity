"""Preserve source-native, undated NG volume/OI facts without inventing sessions.

Explicit pre-2023, six-year, private development-only source extraction.
Raw values are written only to ignored private runtime storage. The receipt
reports integrity/counts but never asserts that a missing ts_ref was recovered.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / ".work" / "runtime" / "market_truth_development"
YEARS = tuple(range(2010, 2016))
OUTPUT_NAME = "unreferenced-statistics-2010-2015"
STATISTICS = (6, 9)
RECEIPT_LIMIT_BYTES = 1024 * 1024
CHUNK_BYTES = 64 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_source(year: int, receipt: dict) -> tuple[Path, str]:
    items = [
        item for item in receipt["raw_objects"]
        if item.get("family") == "statistics" and (
            item.get("filename") == (
                f"glbx-mdp3-{year}0101-{year}1231.statistics.dbn.zst"
                if year != 2010
                else "glbx-mdp3-20100606-20101231.statistics.dbn.zst"
            )
        )
    ]
    if len(items) != 1 or not re.fullmatch(r"[0-9a-f]{64}", str(items[0].get("sha256", ""))):
        raise ValueError(f"missing pinned statistics source for {year}")
    source = STAGE / "raw_checked" / "statistics" / items[0]["filename"]
    if not source.is_file() or source.is_symlink() or source.resolve().parent != (STAGE / "raw_checked" / "statistics").resolve():
        raise ValueError("unapproved raw statistics location")
    if source.stat().st_size != items[0]["bytes"] or sha256(source) != items[0]["sha256"]:
        raise ValueError(f"statistics source integrity failure for {year}")
    return source, items[0]["sha256"]


def accepted_instruments(year: int) -> set[int]:
    path = STAGE / f"definitions-{year}.csv"
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing curated year definitions {year}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        ids = {int(row["instrument_id"]) for row in csv.DictReader(handle)}
    if not ids:
        raise ValueError(f"empty instrument universe {year}")
    return ids


def extract_year(year: int, receipt: dict, output: Path) -> dict:
    import databento_dbn as dbn

    source, source_hash = expected_source(year, receipt)
    allowed_ids = accepted_instruments(year)
    decoder = dbn.DBNDecoder(compression=dbn.Compression.ZSTD)
    counts: Counter[int] = Counter()
    scanned = 0
    metadata = False
    filename = f"undefined-ref-{year}.csv.gz"
    path = output / filename
    with path.open("xb") as raw:  # noqa: SIM117 - streamed compressed writer owns the wrapped handles
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(["source_year", "source_sha256", "record_ordinal",
                                "instrument_id", "stat_type", "quantity",
                                "ts_event", "ts_recv", "ts_ref", "stat_flags",
                                "missing_reason"])
                with source.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                        for item in decoder.write_and_decode(chunk):
                            if isinstance(item, dbn.Metadata):
                                if str(item.dataset) != "GLBX.MDP3" or str(item.schema) != "statistics":
                                    raise ValueError("unexpected provider dataset/schema")
                                metadata = True
                                continue
                            scanned += 1
                            if not metadata:
                                raise ValueError("DBN metadata not supplied first")
                            if scanned > 20_000_000:
                                raise ValueError("bounded source record budget exceeded")
                            if int(item.instrument_id) not in allowed_ids:
                                continue
                            stat = int(getattr(item.stat_type, "value", item.stat_type))
                            if stat not in STATISTICS or item.pretty_ts_ref is not None:
                                continue
                            # Do not infer the missing trade date from event or receive clocks.
                            counts[stat] += 1
                            writer.writerow([
                                year, source_hash, scanned, int(item.instrument_id),
                                stat, int(item.quantity), str(item.pretty_ts_event),
                                str(item.pretty_ts_recv), "", int(item.stat_flags),
                                "undefined_provider_reference_timestamp",
                            ])
    if not metadata:
        raise ValueError("no provider DBN metadata")
    return {
        "year": year, "source_sha256": source_hash, "source_file": source.name,
        "records_scanned": scanned, "recovered_unreferenced_type6": counts[6],
        "recovered_unreferenced_type9": counts[9],
        "relative_path": filename, "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def run() -> dict:
    if not STAGE.is_dir() or STAGE.is_symlink():
        raise ValueError("private development stage unavailable")
    receipt_path = STAGE / "raw-stage-receipt.json"
    if not receipt_path.is_file() or receipt_path.is_symlink() or receipt_path.stat().st_size > RECEIPT_LIMIT_BYTES:
        raise ValueError("missing bounded source receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("dataset") != "GLBX.MDP3" or receipt.get("protected_confirmation_accessed") is not False:
        raise ValueError("development evidence authority mismatch")
    output = STAGE / OUTPUT_NAME
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite existing private quarantine")
    # Leave any failed attempt in an explicitly incomplete private directory.
    # A later retry creates a new stage without deleting diagnostic evidence.
    output_stage = Path(tempfile.mkdtemp(prefix=OUTPUT_NAME + "-incomplete-", dir=STAGE))
    records: list[dict] = []
    for year in YEARS:
        row = extract_year(year, receipt, output_stage)
        records.append(row)
        print(f"recovered undated {year}: type6={row['recovered_unreferenced_type6']} type9={row['recovered_unreferenced_type9']}", flush=True)
    content = {
        "schema_version": 1, "evidence_class": "development",
        "dataset": "GLBX.MDP3", "product": "NG",
        "data_role": "quarantined_original_undated_statistics_not_model_features",
        "protected_confirmation_accessed": False,
        "session_dates_inferred": 0,
        "source_receipt_sha256": sha256(receipt_path),
        "years": records,
        "totals": {
            "type6": sum(row["recovered_unreferenced_type6"] for row in records),
            "type9": sum(row["recovered_unreferenced_type9"] for row in records),
        },
    }
    (output_stage / "receipt.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    # Promotion is atomic on the same volume; never replace prior evidence.
    # os.rename refuses a pre-existing destination on supported Windows.
    if output.exists() or output.is_symlink():
        raise ValueError("refusing overwrite at final quarantine promotion")
    os.rename(output_stage, output)
    return content


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = run()
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print("UNREFERENCED_RECOVERY_BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    print("UNDATED_RECOVERY_COUNTS " + json.dumps(result["totals"], sort_keys=True))
