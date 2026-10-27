"""Disk-backed, bounded-memory build of verified pre-2023 market facts.

No input discovery: the caller supplies three preflight-approved flat CSV paths.
SQLite handles natural-grain revision uniqueness without an in-memory corpus.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from .attestation import SourceBuildAttestation
from .core import MarketTruthError, _evidence
from .revision import REVISION_GRAINS, sqlite_revision_upsert

BATCH_SIZE = 4096
PARQUET_BATCH_ROWS = 32768
MAX_BATCH_BYTES = 8 * 1024 * 1024
MAX_CSV_FIELD_BYTES = 1024 * 1024
FAMILIES = tuple(REVISION_GRAINS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_checked_source(
    source: Path, expected_sha256: str, stage: Path, family: str
) -> Path:
    """Verify the exact file bytes later parsed, not two path-based snapshots."""
    destination = stage / (family + ".checked.csv")
    digest = hashlib.sha256()
    with source.open("rb") as reader, destination.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
            writer.write(chunk)
    if digest.hexdigest() != expected_sha256:
        raise MarketTruthError("raw input SHA-256 mismatch")
    return destination


def _schema(name: str, pa: Any) -> Any:
    string, float64, int64 = pa.string(), pa.float64(), pa.int64()
    common = [("instrument_id", string)]
    if name == "definitions":
        fields = common + [
            ("venue", string), ("symbol", string), ("expiration", string),
            ("available_at", string), ("event_at", string),
            ("last_trade_at", string), ("contract_size", int64),
            ("quote_unit", string), ("tick_size", float64),
            ("source_vintage_id", string), ("evidence_id", string),
        ]
    elif name == "bars":
        fields = common + [
            ("trade_date", string), ("available_at", string),
            ("event_at", string), ("source_vintage_id", string),
            ("open", float64), ("high", float64), ("low", float64),
            ("close", float64), ("volume", int64), ("evidence_id", string),
        ]
    else:
        fields = common + [
            ("trade_date", string), ("available_at", string),
            ("event_at", string), ("stat_type", string),
            ("value", float64), ("source_vintage_id", string),
            ("evidence_id", string),
        ]
    return pa.schema(fields)


def _staging_record(
    family: str, item: dict[str, Any]
) -> tuple[str, str, str, str]:
    grain = json.dumps([str(item[k]) for k in REVISION_GRAINS[family]], separators=(",", ":"))
    payload = json.dumps(item, sort_keys=True, separators=(",", ":"))
    return grain, item["available_at"], item["evidence_id"], payload


def _flush_batch(
    connection: sqlite3.Connection,
    family: str,
    batch: list[tuple[str, str, str, str]],
) -> None:
    if not batch:
        return
    # One provider-neutral revision contract compiles both eager and SQLite rules.
    try:
        connection.executemany(sqlite_revision_upsert(family), batch)
    except sqlite3.IntegrityError as exc:
        raise MarketTruthError(
            f"ambiguous {family[:-1]} revision at same availability"
        ) from exc
    connection.commit()


def build_streaming_parquet(
    paths: dict[str, Path],
    input_records: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    source_manifest_path: Path,
    config_sha256: dict[str, str],
    normalize_row: Callable[[str, dict[str, str]], dict[str, Any] | None],
    governance: SourceBuildAttestation,
) -> dict[str, Any]:
    """Produce an unadmitted candidate; never mint source-owner claims."""
    # This typed assertion is caller-constructible and has no admission power.
    # Only an independently governed, immutable-content catalog can approve
    # the output for the research reader. Here we check structure and bytes.
    if not isinstance(governance, SourceBuildAttestation):
        raise MarketTruthError("validated source governance attestation required")
    if _sha256(source_manifest_path) != governance.source_manifest_sha256:
        raise MarketTruthError("source governance manifest hash mismatch")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise MarketTruthError("pinned PyArrow runtime required") from exc

    if output_dir.exists() or output_dir.is_symlink():
        raise MarketTruthError("refusing overwrite of existing dataset output")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".market-truth-build-", dir=output_dir.parent))
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(stage / "versions.sqlite")
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA cache_size=-16384")
        connection.execute("CREATE TABLE accepted (instrument_id TEXT PRIMARY KEY) WITHOUT ROWID")
        for family in FAMILIES:
            connection.execute(
                f"CREATE TABLE {family} (grain TEXT NOT NULL, "
                "available_at TEXT NOT NULL, evidence_id TEXT NOT NULL, "
                "payload TEXT NOT NULL, CHECK(length(evidence_id)=64), "
                "PRIMARY KEY(grain, available_at)) WITHOUT ROWID"
            )
        @lru_cache(maxsize=65536)
        def accepted_id(instrument_id: str) -> bool:
            return connection.execute(
                "SELECT 1 FROM accepted WHERE instrument_id=?", (instrument_id,)
            ).fetchone() is not None

        raw_counts: dict[str, int] = {}
        for family in FAMILIES:
            expected = input_records[family]
            path = _stage_checked_source(
                paths[family], expected["sha256"], stage, family
            )
            count = 0
            batch_bytes = 0
            batch: list[tuple[str, str, str, str]] = []
            previous_field_limit = csv.field_size_limit()
            csv.field_size_limit(MAX_CSV_FIELD_BYTES)
            try:
                with path.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream, strict=True)
                    if (
                        not reader.fieldnames
                        or len(reader.fieldnames) != len(set(reader.fieldnames))
                        or any(
                            not name.strip() or name != name.strip()
                            for name in reader.fieldnames
                        )
                    ):
                        raise MarketTruthError("missing or duplicate CSV headers")
                    for row in reader:
                        count += 1
                        if None in row or any(value is None for value in row.values()):
                            raise MarketTruthError("CSV row does not match declared columns")
                        if family != "definitions":
                            instrument_id = str(row.get("instrument_id", ""))
                            if not accepted_id(instrument_id):
                                continue
                        item = normalize_row(family, row)
                        if item is None:
                            continue
                        record = _staging_record(family, item)
                        size = sum(len(value) for value in record)
                        if batch and (
                            len(batch) >= BATCH_SIZE
                            or batch_bytes + size > MAX_BATCH_BYTES
                        ):
                            _flush_batch(connection, family, batch)
                            batch.clear()
                            batch_bytes = 0
                        batch.append(record)
                        batch_bytes += size
                _flush_batch(connection, family, batch)
                batch.clear()
                if family == "definitions":
                    connection.execute(
                        "INSERT OR IGNORE INTO accepted "
                        "SELECT DISTINCT json_extract(payload, '$.instrument_id') "
                        "FROM definitions"
                    )
                    connection.commit()
            except csv.Error as exc:
                raise MarketTruthError("invalid or oversized CSV field") from exc
            finally:
                csv.field_size_limit(previous_field_limit)
            if count != expected["row_count"]:
                raise MarketTruthError("source-to-output audit input count mismatch: " + family)
            path.unlink()
            raw_counts[family] = count

        tables: dict[str, dict[str, Any]] = {}
        for family in FAMILIES:
            parquet_path = stage / (family + ".parquet")
            schema = _schema(family, pa)
            writer = pq.ParquetWriter(parquet_path, schema, compression="zstd", use_dictionary=True)
            try:
                cursor = connection.execute(
                    f"SELECT payload FROM {family} ORDER BY grain, available_at"
                )
                records: list[dict[str, Any]] = []
                byte_count = 0
                for (payload,) in cursor:
                    size = len(payload)
                    if records and (
                        len(records) >= PARQUET_BATCH_ROWS
                        or byte_count + size > MAX_BATCH_BYTES
                    ):
                        writer.write_table(pa.Table.from_pylist(records, schema=schema))
                        records.clear()
                        byte_count = 0
                    records.append(json.loads(payload))
                    byte_count += size
                if records:
                    writer.write_table(pa.Table.from_pylist(records, schema=schema))
            finally:
                writer.close()
            rows = connection.execute(f"SELECT COUNT(*) FROM {family}").fetchone()[0]
            tables[family] = {
                "relative_path": parquet_path.name,
                "sha256": _sha256(parquet_path),
                "rows": rows,
                "bytes": parquet_path.stat().st_size,
                "compression": "zstd",
            }
        if not tables["definitions"]["rows"] or not tables["bars"]["rows"]:
            raise MarketTruthError("market truth requires definitions and OHLCV")
        connection.close()
        connection = None
        (stage / "versions.sqlite").unlink()
        module_root = Path(__file__).parent
        # The generic transformer publishes candidate facts only. Caller-built
        # governance objects have no authority to assert a research scope or
        # protected-boundary status. Those declarations belong exclusively to
        # the source-specific preflight/publisher, and are still not approval.
        metadata = {
            "schema_version": 1,
            "source_sha256": {name: input_records[name]["sha256"] for name in FAMILIES},
            "transform_sha256": {
                name: _sha256(module_root / name)
                for name in (
                    "core.py", "ng.py", "query.py", "protected_reads.py", "streaming.py",
                    "revision.py", "errors.py", "attestation.py"
                )
            },
            "config_sha256": dict(sorted(config_sha256.items())),
            "source_row_reconciliation": {
                name: {
                    "source_rows": raw_counts[name],
                    "normalized_rows": tables[name]["rows"],
                    "excluded_or_exact_retransmissions": raw_counts[name] - tables[name]["rows"],
                }
                for name in FAMILIES
            },
            "tables": tables,
            "source_manifest_sha256": governance.source_manifest_sha256,
        }
        if _sha256(source_manifest_path) != governance.source_manifest_sha256:
            raise MarketTruthError("source manifest mutated during build")
        metadata["content_sha256"] = _evidence(metadata)
        (stage / "manifest.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(stage, output_dir)
        return metadata
    except Exception:
        if connection is not None:
            connection.close()
        shutil.rmtree(stage, ignore_errors=True)
        raise
