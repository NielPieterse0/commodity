from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import requests
from scipy.io import netcdf_file

SOURCE_ID = "ncar_gdex_d084001_gfs_0p25_issued_00utc"
SOURCE_START = date(2015, 1, 15)
SOURCE_END = date(2022, 12, 31)
TEMPERATURE_VARIABLE = "Temperature_height_above_ground"
VERTICAL_COORDINATE_M = 2.0
NCSS_BASE = "https://thredds.rda.ucar.edu/thredds/ncss/grid/"
CATALOG_BASE = "https://thredds.rda.ucar.edu/thredds/catalog/"
ALLOWED_OMISSIONS = {
    "required 2m temperature variable absent from archived lead",
    "archived forecast lead file absent",
}
ANCHORS = (
    {"id": "midwest_chicago", "latitude": 41.8781, "longitude": -87.6298},
    {"id": "northeast_new_york", "latitude": 40.7128, "longitude": -74.0060},
    {"id": "southeast_atlanta", "latitude": 33.7490, "longitude": -84.3880},
    {"id": "south_central_houston", "latitude": 29.7604, "longitude": -95.3698},
)
BBOX = {"north": 42.0, "south": 29.75, "west": -95.25, "east": -74.0}


def requested_leads() -> list[int]:
    return list(range(24, 169, 3))


def _parse_issue_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def validate_issue_date(value: str | date) -> date:
    issue_date = _parse_issue_date(value)
    if issue_date > SOURCE_END:
        raise ValueError(f"issue date crosses protected post-2022 evidence: {issue_date}")
    if issue_date < SOURCE_START:
        raise ValueError(f"issue date precedes frozen weather support: {issue_date}")
    return issue_date


def native_source_path(issue_date: str | date, lead_hours: int) -> str:
    day = validate_issue_date(issue_date)
    if lead_hours not in requested_leads():
        raise ValueError(f"lead outside frozen contract: {lead_hours}")
    stamp = day.strftime("%Y%m%d")
    return f"files/g/d084001/{day.year}/{stamp}/gfs.0p25.{stamp}00.f{lead_hours:03d}.grib2"

def catalog_url(issue_date: str | date) -> str:
    day = validate_issue_date(issue_date)
    stamp = day.strftime("%Y%m%d")
    return f"{CATALOG_BASE}files/g/d084001/{day.year}/{stamp}/catalog.xml"


def ncss_url(issue_date: str | date, lead_hours: int) -> str:
    return NCSS_BASE + native_source_path(issue_date, lead_hours)


def ncss_query_url(issue_date: str | date, lead_hours: int) -> str:
    query = urlencode(
        {
            "var": TEMPERATURE_VARIABLE,
            "vertCoord": "2",
            "north": str(BBOX["north"]),
            "south": str(BBOX["south"]),
            "west": str(BBOX["west"]),
            "east": str(BBOX["east"]),
            "accept": "netcdf3",
        }
    )
    return f"{ncss_url(issue_date, lead_hours)}?{query}"


def resolve_native_grid_point(latitude: float, longitude: float) -> tuple[float, float]:
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"invalid latitude: {latitude}")
    normalized_lon = ((longitude + 180.0) % 360.0) - 180.0
    grid_lat = round(latitude / 0.25) * 0.25
    grid_lon = round(normalized_lon / 0.25) * 0.25
    return (round(grid_lat, 2), round(grid_lon, 2))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def classify_archive_omission(status_code: int, response_text: str) -> str | None:
    text = response_text.lower()
    if status_code == 404 and ("filenotfound" in text or "not found" in text):
        return "archived forecast lead file absent"
    if status_code == 400 and (
        TEMPERATURE_VARIABLE.lower() in text and "not contained" in text
    ):
        return "required 2m temperature variable absent from archived lead"
    return None


def _axis_name(dimensions: tuple[str, ...], candidates: tuple[str, ...]) -> str:
    matches = [name for name in dimensions if any(token in name.lower() for token in candidates)]
    if len(matches) != 1:
        raise ValueError(f"unable to identify unique axis {candidates}: {dimensions}")
    return matches[0]


def _nearest_axis_index(values: np.ndarray, target: float, *, tolerance: float = 1e-6) -> int:
    flattened = np.asarray(values, dtype=float).reshape(-1)
    index = int(np.argmin(np.abs(flattened - target)))
    if abs(float(flattened[index]) - target) > tolerance:
        raise ValueError(f"requested grid coordinate {target} absent; nearest={flattened[index]}")
    return index


def extract_anchor_temperatures(
    payload_path: Path, *, issue_date: str | date, lead_hours: int
) -> list[dict[str, object]]:
    day = validate_issue_date(issue_date)
    if lead_hours not in requested_leads():
        raise ValueError(f"lead outside frozen contract: {lead_hours}")
    with netcdf_file(payload_path, "r", mmap=False) as dataset:
        if TEMPERATURE_VARIABLE not in dataset.variables:
            raise ValueError("required 2m temperature variable absent from subset payload")
        variable = dataset.variables[TEMPERATURE_VARIABLE]
        dimensions = tuple(variable.dimensions)
        lat_dim = _axis_name(dimensions, ("lat",))
        lon_dim = _axis_name(dimensions, ("lon",))
        height_dim = _axis_name(dimensions, ("alt", "height"))
        lat_values = np.asarray(dataset.variables[lat_dim][:], dtype=float)
        lon_values = np.asarray(dataset.variables[lon_dim][:], dtype=float)
        height_values = np.asarray(dataset.variables[height_dim][:], dtype=float)
        height_index = _nearest_axis_index(height_values, VERTICAL_COORDINATE_M)
        data = np.asarray(variable[:], dtype=float)
        normalized_lon_values = ((lon_values + 180.0) % 360.0) - 180.0
        issued = datetime(day.year, day.month, day.day, tzinfo=UTC)
        valid = issued + timedelta(hours=lead_hours)
        rows: list[dict[str, object]] = []
        for anchor in ANCHORS:
            grid_lat, grid_lon = resolve_native_grid_point(
                float(anchor["latitude"]), float(anchor["longitude"])
            )
            lat_index = _nearest_axis_index(lat_values, grid_lat)
            lon_index = _nearest_axis_index(normalized_lon_values, grid_lon)
            selection: list[int] = []
            for axis_index, dim_name in enumerate(dimensions):
                if dim_name == lat_dim:
                    selection.append(lat_index)
                elif dim_name == lon_dim:
                    selection.append(lon_index)
                elif dim_name == height_dim:
                    selection.append(height_index)
                elif int(variable.shape[axis_index]) == 1:
                    selection.append(0)
                else:
                    raise ValueError(f"unexpected non-singleton temperature dimension: {dim_name}")
            temperature_k = float(data[tuple(selection)])
            rows.append(
                {
                    "issued_at": issued.isoformat().replace("+00:00", "Z"),
                    "forecast_valid_at": valid.isoformat().replace("+00:00", "Z"),
                    "lead_hours": lead_hours,
                    "anchor_id": str(anchor["id"]),
                    "temperature_k": temperature_k,
                    "temperature_c": temperature_k - 273.15,
                    "resolved_grid_latitude": grid_lat,
                    "resolved_grid_longitude": grid_lon,
                }
            )
    return rows


def _file_metadata(path: Path) -> dict[str, object]:
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}

def build_daily_manifest(
    *,
    issue_date: str | date,
    available_leads: Iterable[int],
    missing_leads: Iterable[Mapping[str, object]],
    files: Iterable[Path],
) -> dict[str, object]:
    day = validate_issue_date(issue_date)
    available = sorted({int(value) for value in available_leads})
    if any(value not in requested_leads() for value in available):
        raise ValueError("available lead outside frozen contract")
    missing = [
        {"lead_hours": int(item["lead_hours"]), "reason": str(item["reason"])}
        for item in missing_leads
    ]
    if any(item["reason"] not in ALLOWED_OMISSIONS for item in missing):
        raise ValueError("unapproved archive omission reason")
    if set(available) & {int(item["lead_hours"]) for item in missing}:
        raise ValueError("lead cannot be both available and missing")
    file_paths = sorted((Path(path) for path in files), key=lambda path: path.name)
    return {
        "schema_version": 1,
        "source_id": SOURCE_ID,
        "issue_date": day.isoformat(),
        "cycle_utc_hour": 0,
        "requested_forecast_lead_hours": requested_leads(),
        "forecast_lead_hours": available,
        "archive_missing_leads": missing,
        "anchor_ids": [str(anchor["id"]) for anchor in ANCHORS],
        "record_count": len(available) * len(ANCHORS),
        "payload_count": len(available),
        "files": {path.name: _file_metadata(path) for path in file_paths},
    }

_THREAD_LOCAL = threading.local()


def _session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "commodity-issue455-weather-recovery/1"})
        _THREAD_LOCAL.session = session
    return session


def _catalog_entries(content: bytes) -> tuple[str, dict[int, dict[str, object]]]:
    root = ET.fromstring(content)
    namespace = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}
    pattern = re.compile(r"gfs\.0p25\.(\d{8})00\.f(\d{3})\.grib2$")
    entries: dict[int, dict[str, object]] = {}
    issue_stamp: str | None = None
    for dataset in root.findall(".//t:dataset", namespace):
        name = str(dataset.attrib.get("name", ""))
        match = pattern.fullmatch(name)
        if not match:
            continue
        issue_stamp = issue_stamp or match.group(1)
        lead = int(match.group(2))
        size = dataset.find("t:dataSize", namespace)
        modified = dataset.find("t:date[@type='modified']", namespace)
        entries[lead] = {
            "name": name,
            "url_path": str(dataset.attrib.get("urlPath", "")),
            "data_size": None if size is None else (size.text or "").strip(),
            "data_size_units": None if size is None else size.attrib.get("units"),
            "modified": None if modified is None else (modified.text or "").strip(),
        }
    if issue_stamp is None:
        raise ValueError("GDEX daily catalog contains no GFS 0.25-degree files")
    return issue_stamp, entries

def fetch_catalog(
    issue_date: str | date,
    *,
    timeout_seconds: float = 30.0,
    retries: int = 4,
) -> dict[str, object]:
    day = validate_issue_date(issue_date)
    url = catalog_url(day)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = _session().get(url, timeout=timeout_seconds)
            response.raise_for_status()
            stamp, entries = _catalog_entries(response.content)
            if stamp != day.strftime("%Y%m%d"):
                raise ValueError(f"catalog date identity mismatch: expected {day}, found {stamp}")
            return {
                "url": url,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "bytes": len(response.content),
                "entries": entries,
            }
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(8.0, float(2 ** (attempt - 1))))
    assert last_error is not None
    raise RuntimeError(f"failed GDEX catalog after {retries} attempts: {day}") from last_error


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_write_bytes(path, text.encode("utf-8"))


def _valid_netcdf3(content: bytes) -> bool:
    return len(content) >= 512 and content[:3] == b"CDF"


def download_lead_payload(
    issue_date: str | date,
    lead_hours: int,
    destination: Path,
    *,
    retries: int = 4,
    timeout_seconds: float = 60.0,
) -> dict[str, object]:
    day = validate_issue_date(issue_date)
    url = ncss_query_url(day, lead_hours)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = _session().get(url, timeout=timeout_seconds)
            if response.status_code != 200:
                reason = classify_archive_omission(response.status_code, response.text[:2000])
                if reason is not None:
                    return {"status": "missing", "lead_hours": lead_hours, "reason": reason, "url": url}
                response.raise_for_status()
            if not _valid_netcdf3(response.content):
                raise ValueError(
                    f"invalid NetCDF3 payload for {day} lead {lead_hours}: {len(response.content)} bytes"
                )
            _atomic_write_bytes(destination, response.content)
            return {
                "status": "available",
                "lead_hours": lead_hours,
                "url": url,
                "payload": destination,
                "sha256": sha256_file(destination),
                "bytes": destination.stat().st_size,
            }
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(8.0, float(2 ** (attempt - 1))))
    assert last_error is not None
    raise RuntimeError(f"failed GDEX subset after {retries} attempts: {day} lead {lead_hours}") from last_error


def _write_anchor_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    fields = ["issued_at", "forecast_valid_at", "lead_hours", "anchor_id", "temperature_c"]
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row[field] for field in fields})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _manifest_is_complete(day_dir: Path, issue_date: date) -> bool:
    manifest_path = day_dir / "manifest.json"
    lineage_path = day_dir / "lineage.json"
    if not manifest_path.is_file() or not lineage_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_id") != SOURCE_ID or manifest.get("issue_date") != issue_date.isoformat():
            return False
        actual = {int(value) for value in manifest.get("forecast_lead_hours", [])}
        missing = {int(item["lead_hours"]) for item in manifest.get("archive_missing_leads", [])}
        if actual | missing != set(requested_leads()) or actual & missing:
            return False
        for name, metadata in manifest.get("files", {}).items():
            path = day_dir / str(name)
            if not path.is_file() or path.stat().st_size != int(metadata["bytes"]):
                return False
            if sha256_file(path) != str(metadata["sha256"]):
                return False
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return False
    return True


def _lead_payload_name(lead_hours: int) -> str:
    return f"gfs_00z_f{lead_hours:03d}_2m.nc"


def _recover_available_lead(day: date, lead_hours: int, day_dir: Path) -> dict[str, object]:
    payload_path = day_dir / _lead_payload_name(lead_hours)
    if payload_path.is_file():
        try:
            rows = extract_anchor_temperatures(payload_path, issue_date=day, lead_hours=lead_hours)
            return {
                "status": "available",
                "lead_hours": lead_hours,
                "url": ncss_query_url(day, lead_hours),
                "payload": payload_path,
                "sha256": sha256_file(payload_path),
                "bytes": payload_path.stat().st_size,
                "rows": rows,
                "resumed": True,
            }
        except (IndexError, KeyError, OSError, OverflowError, TypeError, ValueError):
            pass
    last_error: Exception | None = None
    for attempt in range(1, 9):
        try:
            result = download_lead_payload(day, lead_hours, payload_path, retries=1)
            if result["status"] == "missing":
                return result
            result["rows"] = extract_anchor_temperatures(
                payload_path, issue_date=day, lead_hours=lead_hours
            )
            result["resumed"] = False
            return result
        except (
            IndexError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            last_error = exc
            if attempt < 8:
                time.sleep(min(15.0, float(2 ** (attempt - 1))))
    assert last_error is not None
    raise RuntimeError(
        f"failed validated GDEX subset after 8 attempts: {day} lead {lead_hours}"
    ) from last_error


def recover_day(
    issue_date: str | date,
    output_root: Path,
    *,
    workers: int = 12,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    day = validate_issue_date(issue_date)
    stamp = day.strftime("%Y%m%d")
    day_dir = Path(output_root) / "weather" / "gfs_rda_025" / str(day.year) / stamp
    day_dir.mkdir(parents=True, exist_ok=True)
    if _manifest_is_complete(day_dir, day):
        return {"issue_date": day.isoformat(), "status": "skipped_complete", "path": str(day_dir)}
    catalog = fetch_catalog(day, timeout_seconds=timeout_seconds)
    catalog_entries = catalog["entries"]
    assert isinstance(catalog_entries, dict)
    missing: list[dict[str, object]] = []
    results: dict[int, dict[str, object]] = {}
    available_catalog_leads: list[int] = []
    for lead in requested_leads():
        if lead not in catalog_entries:
            missing.append(
                {"lead_hours": lead, "reason": "archived forecast lead file absent"}
            )
        else:
            available_catalog_leads.append(lead)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_recover_available_lead, day, lead, day_dir): lead
            for lead in available_catalog_leads
        }
        for future in as_completed(futures):
            lead = futures[future]
            result = future.result()
            if result["status"] == "missing":
                missing.append({"lead_hours": lead, "reason": str(result["reason"])})
            else:
                results[lead] = result
    missing.sort(key=lambda item: int(item["lead_hours"]))
    available = sorted(results)
    if set(available) | {int(item["lead_hours"]) for item in missing} != set(requested_leads()):
        raise RuntimeError(f"incomplete lead accounting for {day}")
    rows = [row for lead in available for row in results[lead]["rows"]]
    csv_path = day_dir / "anchor_temperature.csv"
    _write_anchor_csv(csv_path, rows)
    files = [csv_path] + [Path(results[lead]["payload"]) for lead in available]
    manifest = build_daily_manifest(
        issue_date=day,
        available_leads=available,
        missing_leads=missing,
        files=files,
    )
    _write_json(day_dir / "manifest.json", manifest)
    lineage = {
        "schema_version": 1,
        "issue": 455,
        "source_id": SOURCE_ID,
        "issue_date": day.isoformat(),
        "catalog": {
            "url": catalog["url"],
            "sha256": catalog["sha256"],
            "bytes": catalog["bytes"],
        },
        "extraction": {
            "temperature_variable": TEMPERATURE_VARIABLE,
            "vertical_coordinate_m": VERTICAL_COORDINATE_M,
            "subset_bbox": BBOX,
            "subset_format": "netcdf3",
            "fill_policy": "none",
            "anchor_selection": "deterministic native-grid nearest neighbour",
        },
        "anchors": [
            {
                **anchor,
                "resolved_grid_latitude": resolve_native_grid_point(
                    float(anchor["latitude"]), float(anchor["longitude"])
                )[0],
                "resolved_grid_longitude": resolve_native_grid_point(
                    float(anchor["latitude"]), float(anchor["longitude"])
                )[1],
            }
            for anchor in ANCHORS
        ],
        "leads": [],
    }
    lead_lineage = lineage["leads"]
    assert isinstance(lead_lineage, list)
    missing_by_lead = {int(item["lead_hours"]): item for item in missing}
    for lead in requested_leads():
        native_entry = catalog_entries.get(lead)
        if lead in missing_by_lead:
            lead_lineage.append(
                {
                    "lead_hours": lead,
                    "status": "missing",
                    "reason": missing_by_lead[lead]["reason"],
                    "native_source_path": native_source_path(day, lead),
                    "native_catalog_entry": native_entry,
                }
            )
            continue
        result = results[lead]
        lead_lineage.append(
            {
                "lead_hours": lead,
                "status": "available",
                "native_source_path": native_source_path(day, lead),
                "native_catalog_entry": native_entry,
                "subset_url": result["url"],
                "subset_file": Path(result["payload"]).name,
                "subset_sha256": result["sha256"],
                "subset_bytes": result["bytes"],
                "resumed": bool(result.get("resumed", False)),
            }
        )
    _write_json(day_dir / "lineage.json", lineage)
    if not _manifest_is_complete(day_dir, day):
        raise RuntimeError(f"reconstructed day failed self-verification: {day}")
    return {
        "issue_date": day.isoformat(),
        "status": "recovered",
        "available_leads": len(available),
        "missing_leads": len(missing),
        "path": str(day_dir),
    }


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_manifest_index(output_root: Path) -> dict[str, object]:
    root = Path(output_root)
    weather_root = root / "weather" / "gfs_rda_025"
    identities: list[dict[str, object]] = []
    lineage_identities: list[dict[str, object]] = []
    issue_dates: list[str] = []
    missing_lead_count = 0
    for manifest_path in sorted(weather_root.glob("*/*/manifest.json")):
        day_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        issue_date = validate_issue_date(str(manifest["issue_date"]))
        if not _manifest_is_complete(day_dir, issue_date):
            raise RuntimeError(f"incomplete reconstructed day in manifest index: {issue_date}")
        relative_manifest = manifest_path.relative_to(root).as_posix()
        identities.append({"path": relative_manifest, "sha256": sha256_file(manifest_path)})
        lineage_path = day_dir / "lineage.json"
        lineage_identities.append(
            {"path": lineage_path.relative_to(root).as_posix(), "sha256": sha256_file(lineage_path)}
        )
        issue_dates.append(issue_date.isoformat())
        missing_lead_count += len(manifest.get("archive_missing_leads", []))
    expected_dates = [
        (SOURCE_START + timedelta(days=offset)).isoformat()
        for offset in range((SOURCE_END - SOURCE_START).days + 1)
    ]
    return {
        "schema_version": 1,
        "issue": 455,
        "source_id": SOURCE_ID,
        "snapshot_count": len(issue_dates),
        "expected_snapshot_count": len(expected_dates),
        "complete": issue_dates == expected_dates,
        "earliest_preserved": issue_dates[0] if issue_dates else None,
        "latest_preserved": issue_dates[-1] if issue_dates else None,
        "archive_missing_lead_count": missing_lead_count,
        "legacy_manifest_index_sha256": _sha256_payload(identities),
        "lineage_index_sha256": _sha256_payload(lineage_identities),
        "manifest_identities": identities,
        "lineage_identities": lineage_identities,
    }


def recover_range(
    start: str | date,
    end: str | date,
    output_root: Path,
    *,
    workers: int = 12,
) -> list[dict[str, object]]:
    start_day = validate_issue_date(start)
    end_day = validate_issue_date(end)
    if end_day < start_day:
        raise ValueError("end date precedes start date")
    outcomes: list[dict[str, object]] = []
    day = start_day
    while day <= end_day:
        outcome = recover_day(day, output_root, workers=workers)
        outcomes.append(outcome)
        print(json.dumps(outcome, sort_keys=True), flush=True)
        day += timedelta(days=1)
    return outcomes


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover issue-455 GDEX weather inputs.")
    parser.add_argument("--start", default=SOURCE_START.isoformat())
    parser.add_argument("--end", default=SOURCE_END.isoformat())
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_default_repo_root() / "data" / "raw" / "issue455",
    )
    parser.add_argument("--write-index", type=Path)
    args = parser.parse_args()
    recover_range(args.start, args.end, args.output_root, workers=args.workers)
    index = build_manifest_index(args.output_root)
    index_path = args.write_index
    if index_path is None:
        index_path = (
            _default_repo_root()
            / "research"
            / "programmes"
            / "004-v2-maximum-reproducible-one-month-return"
            / "issue455-gfs-manifest-index-v1.json"
        )
    _write_json(index_path, index)
    print(json.dumps({"manifest_index": str(index_path), "complete": index["complete"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
