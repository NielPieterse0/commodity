"""Verified Parquet-backed causal market snapshot API for V3.

Only named files in a previously verified private development dataset are opened.
The reader never enumerates a provider archive or protected confirmation namespace.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from . import approval as owner_approval
from .core import (
    MarketTruthError,
    _evidence,
    assert_development_date,
    parse_date,
    parse_time,
    snapshot_asof,
)
from .protected_reads import protected_table_reads

TABLES = frozenset({"definitions", "bars", "statistics"})
MAX_MANIFEST_BYTES = 1_048_576
MAX_PARQUET_BYTES = 128 * 1024**3
MAX_APPROVAL_CATALOG_BYTES = 1_048_576
# Tracked source-owner admission policy, not a digest supplied with the dataset.
DEFAULT_APPROVAL_CATALOG = (
    Path(__file__).resolve().parents[3]
    / "data" / "manifests" / "ng-phase2-market-truth.json"
)
DEFAULT_APPROVED_ROOT = (
    Path(__file__).resolve().parents[3]
    / ".work"
    / "runtime"
    / "market_truth_development"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_independent_admission(
    manifest: dict[str, Any], *, catalog_path: Path,
    trusted_signers: Mapping[str, tuple[bytes, str]],
) -> None:
    """Require a separately governed content pin; build output cannot self-approve."""
    path = catalog_path
    if path.is_symlink() or not path.is_file():
        raise MarketTruthError("trusted source-owner admission catalog missing")
    with path.open("rb") as reader:
        raw = reader.read(MAX_APPROVAL_CATALOG_BYTES + 1)
    if len(raw) > MAX_APPROVAL_CATALOG_BYTES:
        raise MarketTruthError("source-owner admission catalog too large")
    try:
        catalog = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise MarketTruthError("invalid source-owner admission catalog") from exc
    if (
        not isinstance(catalog, dict)
        or not {"schema_version", "authority", "datasets"}.issubset(catalog)
        or catalog["schema_version"] != 2
        or catalog["authority"] != "governed_source_owner_review"
        or not isinstance(catalog["datasets"], list)
    ):
        raise MarketTruthError("invalid source-owner admission policy")
    approved = []
    identities: set[str] = set()
    for item in catalog["datasets"]:
        if not isinstance(item, dict) or set(item) != {
            "content_sha256", "source_manifest_sha256", "source_sha256",
            "tables_sha256", "source_review_id", "local_evidence_verified",
        }:
            raise MarketTruthError("invalid source-owner approval record")
        identity = item["content_sha256"]
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise MarketTruthError("invalid approved dataset identity")
        if identity in identities:
            raise MarketTruthError("duplicate source-owner approval")
        identities.add(identity)
        if identity == manifest["content_sha256"]:
            approved.append(item)
    # Matching hashes and arbitrary review text never prove ownership.
    # Signed authority is required before any nonempty catalog may admit data.
    owner_approval.verify_catalog_signature(
        catalog, catalog_sha256=hashlib.sha256(raw).hexdigest(),
        trusted_signers=trusted_signers,
    )
    if len(approved) != 1:
        raise MarketTruthError("dataset has no independent source-owner approval")
    item = approved[0]
    if (
        not isinstance(item["source_review_id"], str)
        or not item["source_review_id"].strip()
        or item["local_evidence_verified"] is not True
        or item["source_manifest_sha256"] != manifest.get("source_manifest_sha256")
        or item["source_sha256"] != manifest.get("source_sha256")
        or item["tables_sha256"] != {
            family: manifest["tables"][family]["sha256"] for family in TABLES
        }
    ):
        raise MarketTruthError("source-owner approval does not match dataset evidence")


class MarketTruthDataset:
    """Dataset admitted by independent source-owner pins and checked table bytes."""

    def __init__(self, location: Path, *, expected_content_sha256: str):
        # The caller digest is a comparison only, never an approval token.
        # Authoritative admission comes separately from the governed catalog.
        if not isinstance(expected_content_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_content_sha256
        ):
            raise MarketTruthError("trusted dataset manifest digest required")
        location = Path(location)
        # A caller-supplied root is not authorization. The private development
        # boundary is owned by the deployment, not by untrusted data callers.
        root = DEFAULT_APPROVED_ROOT.resolve(strict=False)
        if location.is_symlink():
            raise MarketTruthError("dataset symlink prohibited")
        self.location = location.resolve(strict=True)
        self._trusted_root = root
        if self.location == root or self.location.parent != root:
            raise MarketTruthError("dataset outside approved development-only root")
        manifest_path = self.location / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise MarketTruthError("market truth manifest missing or symlinked")
        with manifest_path.open("rb") as reader:
            manifest_bytes = reader.read(MAX_MANIFEST_BYTES + 1)
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise MarketTruthError("market truth manifest exceeds size limit")
        self._manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self.manifest = json.loads(manifest_bytes.decode("utf-8"))
        manifest = self.manifest
        if (
            manifest.get("schema_version") != 1
            or manifest.get("dataset_scope") != "development_pre2023"
            or manifest.get("protected_confirmation_accessed") is not False
            or set(manifest.get("tables", {})) != TABLES
        ):
            raise MarketTruthError("invalid development dataset manifest")
        expected = manifest.get("content_sha256")
        actual = _evidence({k: v for k, v in manifest.items() if k != "content_sha256"})
        if expected != actual or expected != expected_content_sha256:
            raise MarketTruthError("dataset manifest identity mismatch")
        self._approval_catalog_path = DEFAULT_APPROVAL_CATALOG
        _assert_independent_admission(
            manifest, catalog_path=self._approval_catalog_path,
            trusted_signers=owner_approval.TRUSTED_SIGNERS,
        )
        self.files: dict[str, Path] = {}
        for name in sorted(TABLES):
            info = manifest["tables"][name]
            if not isinstance(info, dict):
                raise MarketTruthError("malformed table metadata")
            if (
                info.get("relative_path") != f"{name}.parquet"
                or info.get("compression") != "zstd"
            ):
                raise MarketTruthError(
                    "unexpected market table location or compression"
                )
            path = self.location / f"{name}.parquet"
            if not path.is_file() or path.is_symlink():
                raise MarketTruthError("market table missing or symlinked")
            if (
                type(info.get("rows")) is not int
                or info["rows"] < 0
                or type(info.get("bytes")) is not int
                or not 0 < info["bytes"] <= MAX_PARQUET_BYTES
                or not isinstance(info.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"])
            ):
                raise MarketTruthError(f"invalid market table metadata: {name}")
            if path.stat().st_size != info["bytes"]:
                raise MarketTruthError(f"market table size mismatch: {name}")
            if _sha256(path) != info["sha256"]:
                raise MarketTruthError(f"market table checksum failure: {name}")
            try:
                import pyarrow.parquet as pq
            except ImportError as exc:
                raise MarketTruthError("pinned Parquet metadata runtime required") from exc
            try:
                actual_rows = pq.read_metadata(path).num_rows
            except (OSError, ValueError) as exc:
                raise MarketTruthError(
                    f"unreadable market table metadata: {name}"
                ) from exc
            if actual_rows != info["rows"]:
                raise MarketTruthError(f"market table row-count mismatch: {name}")
            self.files[name] = path

    def _assert_sources_unchanged(self) -> None:
        manifest_path = self.location / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise MarketTruthError("market truth manifest changed or removed")
        if _sha256(manifest_path) != self._manifest_sha256:
            raise MarketTruthError("market truth manifest mutated after opening")
        # Recheck independent policy as well as file identity; an existing
        # reader may not continue after the approved content pin is revoked.
        # Re-resolve current trust on every snapshot: stale existing readers
        # cannot continue after the signer or approved catalog pin is revoked.
        _assert_independent_admission(
            self.manifest, catalog_path=self._approval_catalog_path,
            trusted_signers=owner_approval.TRUSTED_SIGNERS,
        )
        # Trusted, externally enforced immutable storage is still required
        # to exclude concurrent writers between checks and DuckDB opens.
        if (
            self.location.is_symlink()
            or self.location.resolve(strict=True).parent != self._trusted_root
        ):
            raise MarketTruthError("market dataset escaped approved root")
        for name, path in self.files.items():
            if (
                path.is_symlink()
                or not path.is_file()
                or path.resolve(strict=True).parent != self.location
            ):
                raise MarketTruthError(f"market table path changed: {name}")
            if path.stat().st_size != self.manifest["tables"][name]["bytes"]:
                raise MarketTruthError(f"market table size mismatch: {name}")
            if _sha256(path) != self.manifest["tables"][name]["sha256"]:
                raise MarketTruthError(f"market table checksum failure: {name}")

    @staticmethod
    def _select(
        connection: Any, statement: str, params: list[Any], *, limit: int
    ) -> list[dict[str, Any]]:
        """Bound Python memory even if a future SQL edit broadens a scan."""
        cursor = connection.execute(statement, params)
        names = [item[0] for item in cursor.description]
        rows: list[dict[str, Any]] = []
        while batch := cursor.fetchmany(min(128, limit + 1 - len(rows))):
            rows.extend(dict(zip(names, row, strict=True)) for row in batch)
            if len(rows) > limit:
                raise MarketTruthError("market snapshot result exceeds row limit")
        return rows

    def _curve_from_parquet(
        self, connection: Any, day: date, cutoff: datetime, ranks: int
    ) -> list[dict[str, Any]]:
        """Push latest-version selection and rank pruning into DuckDB."""
        membership = min(
            cutoff, datetime.combine(day, time.max, tzinfo=UTC)
        ).isoformat()
        from .ng_expiry import (
            UNQUALIFIED_NG_EXPIRIES,
            fence_ng_expiry_definitions,
            verify_ng_expiry_policy,
        )

        # Check the full 14-contract exact-source cohort BEFORE expiry/rank
        # pruning. The old +/-8-day SQL scan could miss already-expired
        # candidates and incorrectly promote later contracts to M1..M12.
        # The pinned delivery-month bound separately proves when a contract
        # cannot legally remain eligible, independent of CME holiday versions.
        verify_ng_expiry_policy()
        symbols = sorted({symbol for symbol, _ in UNQUALIFIED_NG_EXPIRIES})
        placeholders = ", ".join("?" for _ in symbols)
        boundary = self._select(
            connection,
            f"""
            SELECT DISTINCT venue, symbol, expiration
            FROM read_parquet(?)
            WHERE venue = 'NYMEX'
              AND CAST(available_at AS TIMESTAMPTZ) <= CAST(? AS TIMESTAMPTZ)
              AND symbol IN ({placeholders})
            """,
            [str(self.files["definitions"]), membership, *symbols],
            limit=1024,
        )
        fence_ng_expiry_definitions(boundary, datetime.fromisoformat(membership))
        definitions = self._select(
            connection,
            """
            WITH latest AS (
                SELECT * FROM read_parquet(?)
                WHERE CAST(available_at AS TIMESTAMPTZ) <=
                      CAST(? AS TIMESTAMPTZ)
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY venue, instrument_id
                    ORDER BY CAST(available_at AS TIMESTAMPTZ) DESC,
                             evidence_id DESC
                ) = 1
            ), eligible AS (
                SELECT * FROM latest
                WHERE CAST(COALESCE(last_trade_at, expiration)
                           AS TIMESTAMPTZ) > CAST(? AS TIMESTAMPTZ)
            ), marked AS (
                SELECT *, COUNT(*) OVER (
                    PARTITION BY venue, symbol
                ) AS alias_count FROM eligible
            )
            SELECT *, MAX(CASE WHEN alias_count > 1 THEN 1 ELSE 0 END)
                      OVER () AS any_alias_conflict
            FROM marked
            ORDER BY CAST(expiration AS TIMESTAMPTZ),
                     venue, symbol, instrument_id
            LIMIT ?
            """,
            [str(self.files["definitions"]), membership, membership, ranks],
            limit=ranks,
        )
        if any(row.pop("any_alias_conflict") for row in definitions):
            raise MarketTruthError("ambiguous source contract alias mapping")
        definitions = fence_ng_expiry_definitions(
            definitions, datetime.fromisoformat(membership)
        )
        for row in definitions:
            row.pop("alias_count")
        keys = [row["instrument_id"] for row in definitions]
        bars: list[dict[str, Any]] = []
        statistics: list[dict[str, Any]] = []
        if keys:
            placeholders = ", ".join("?" for _ in keys)
            for family, grain, result, limit in (
                ("bars", "instrument_id, trade_date", bars, ranks),
                ("statistics", "instrument_id, trade_date, stat_type",
                 statistics, ranks * 3),
            ):
                result.extend(self._select(
                    connection,
                    "SELECT * FROM read_parquet(?) WHERE trade_date = ? "
                    "AND CAST(available_at AS TIMESTAMPTZ) <= "
                    "CAST(? AS TIMESTAMPTZ) "
                    f"AND instrument_id IN ({placeholders}) "
                    f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {grain} "
                    "ORDER BY CAST(available_at AS TIMESTAMPTZ) DESC, "
                    "evidence_id DESC) = 1",
                    [str(self.files[family]), day.isoformat(),
                     cutoff.isoformat(), *keys],
                    limit=limit,
                ))
        from .core import curve_asof

        return curve_asof(
            {"definitions": definitions, "bars": bars, "statistics": statistics},
            day, cutoff, ranks=ranks,
        )

    def snapshot(
        self,
        session: date | str,
        decision_time: datetime | str,
        *,
        session_history: Iterable[date | str] = (),
    ) -> dict[str, Any]:
        """Query only eligible session grains; never joins future-available values."""
        target = parse_date(session)
        cutoff = parse_time(decision_time)
        assert_development_date(target)
        assert_development_date(cutoff.date())
        if target > cutoff.date():
            raise MarketTruthError("session after query time")
        history = sorted(
            {parse_date(day) for day in session_history if parse_date(day) < target}
        )
        for day in history:
            assert_development_date(day)
        # Only the final 20 sessions affect returned momentum, volatility,
        # jumps and prior-roll fields; avoid scanning arbitrary older history.
        history = history[-20:]
        try:
            import duckdb
        except ImportError as exc:
            raise MarketTruthError(
                "DuckDB 1.5 runtime is required for Parquet queries"
            ) from exc
        # On Windows, retained no-write/no-delete-share handles exclude
        # active mutation between the last checksum and DuckDB's path open.
        # Other platforms still require independently proven immutable storage.
        with protected_table_reads(
            [self.location / "manifest.json", self._approval_catalog_path, *self.files.values()]
        ):
            self._assert_sources_unchanged()
            con = duckdb.connect(database=":memory:")
            try:
                con.execute("SET memory_limit='512MB'")
                con.execute("SET TimeZone='UTC'")
                from .ng_expiry import model_safe_ng_curve

                result = snapshot_asof(
                    {"source_sha256": self.manifest.get("source_sha256", {})},
                    target,
                    cutoff,
                    session_history=history,
                    curve_lookup=lambda day, ranks: model_safe_ng_curve(
                        self._curve_from_parquet(con, day, cutoff, ranks)
                    ),
                )
            finally:
                con.close()
            self._assert_sources_unchanged()
        result["dataset_content_sha256"] = self.manifest["content_sha256"]
        result["dataset_source_sha256"] = self.manifest.get("source_sha256", {})
        return result
