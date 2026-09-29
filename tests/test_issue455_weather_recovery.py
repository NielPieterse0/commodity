from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "research" / "recover_issue455_weather.py"
POWER_SCRIPT_PATH = REPO_ROOT / "scripts" / "research" / "run_issue455_power_weather.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("recover_issue455_weather", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_power_module():
    spec = importlib.util.spec_from_file_location("run_issue455_power_weather", POWER_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_source_path_and_requested_leads() -> None:
    recovery = _load_module()
    assert recovery.requested_leads() == list(range(24, 169, 3))
    assert recovery.native_source_path("2015-01-15", 24) == (
        "files/g/d084001/2015/20150115/gfs.0p25.2015011500.f024.grib2"
    )

def test_native_grid_resolution_matches_gdex_probe() -> None:
    recovery = _load_module()
    expected = {
        "midwest_chicago": (42.0, -87.75),
        "northeast_new_york": (40.75, -74.0),
        "southeast_atlanta": (33.75, -84.5),
        "south_central_houston": (29.75, -95.25),
    }
    for anchor in recovery.ANCHORS:
        assert recovery.resolve_native_grid_point(anchor["latitude"], anchor["longitude"]) == expected[
            anchor["id"]
        ]


def test_protected_date_boundary_is_fail_closed() -> None:
    recovery = _load_module()
    recovery.validate_issue_date("2022-12-31")
    with pytest.raises(ValueError, match="protected"):
        recovery.validate_issue_date("2023-01-01")
    with pytest.raises(ValueError, match="support"):
        recovery.validate_issue_date("2015-01-14")


def test_archive_omission_classification_is_bounded() -> None:
    recovery = _load_module()
    assert recovery.classify_archive_omission(404, "FileNotFound") == "archived forecast lead file absent"
    assert recovery.classify_archive_omission(400, "Temperature_height_above_ground is not contained") == (
        "required 2m temperature variable absent from archived lead"
    )
    assert recovery.classify_archive_omission(500, "server error") is None


def _write_temperature_payload(path: Path) -> None:
    with netcdf_file(path, "w") as dataset:
        dataset.createDimension("alt", 3)
        dataset.createDimension("latitude", 4)
        dataset.createDimension("longitude", 4)
        alt = dataset.createVariable("alt", "f8", ("alt",))
        lat = dataset.createVariable("latitude", "f4", ("latitude",))
        lon = dataset.createVariable("longitude", "f4", ("longitude",))
        temp = dataset.createVariable(
            "Temperature_height_above_ground", "f4", ("alt", "latitude", "longitude")
        )
        alt[:] = np.array([2.0, 80.0, 100.0])
        lat[:] = np.array([42.0, 40.75, 33.75, 29.75])
        lon[:] = np.array([-87.75, -74.0, -84.5, -95.25])
        values = np.full((3, 4, 4), 999.0, dtype=np.float32)
        values[0, 0, 0] = 268.24
        values[0, 1, 1] = 271.87
        values[0, 2, 2] = 275.70
        values[0, 3, 3] = 281.74
        temp[:] = values


def test_extract_anchor_temperatures_selects_only_2m(tmp_path: Path) -> None:
    recovery = _load_module()
    payload = tmp_path / "lead.nc"
    _write_temperature_payload(payload)
    rows = recovery.extract_anchor_temperatures(payload, issue_date="2015-01-15", lead_hours=24)
    assert [row["anchor_id"] for row in rows] == [anchor["id"] for anchor in recovery.ANCHORS]
    assert [row["temperature_k"] for row in rows] == pytest.approx([268.24, 271.87, 275.70, 281.74])
    assert all(row["forecast_valid_at"] == "2015-01-16T00:00:00Z" for row in rows)


def test_daily_manifest_preserves_missing_leads_without_fill(tmp_path: Path) -> None:
    recovery = _load_module()
    payload = tmp_path / "f024.nc"
    payload.write_text("probe payload\n", encoding="utf-8")
    csv_path = tmp_path / "anchor_temperature.csv"
    csv_path.write_text(
        "issued_at,forecast_valid_at,lead_hours,anchor_id,temperature_c\n", encoding="utf-8"
    )
    manifest = recovery.build_daily_manifest(
        issue_date="2015-01-15",
        available_leads=[24],
        missing_leads=[{"lead_hours": 27, "reason": "archived forecast lead file absent"}],
        files=[payload, csv_path],
    )
    assert manifest["requested_forecast_lead_hours"] == list(range(24, 169, 3))
    assert manifest["forecast_lead_hours"] == [24]
    assert manifest["archive_missing_leads"] == [
        {"lead_hours": 27, "reason": "archived forecast lead file absent"}
    ]
    assert manifest["record_count"] == 4
    assert manifest["payload_count"] == 1
    assert manifest["anchor_ids"] == [anchor["id"] for anchor in recovery.ANCHORS]
    assert set(manifest["files"]) == {"f024.nc", "anchor_temperature.csv"}


def test_recover_available_lead_retries_invalid_http200_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery = _load_module()
    attempts = {"count": 0}

    def fake_download(day, lead_hours, destination, *, retries):
        attempts["count"] += 1
        destination.write_text(f"attempt-{attempts['count']}", encoding="utf-8")
        return {"status": "available", "payload": destination, "lead_hours": lead_hours}

    def fake_extract(payload_path, *, issue_date, lead_hours):
        if attempts["count"] == 1:
            raise ValueError("truncated NetCDF payload")
        return [{"anchor_id": "ok"}]

    monkeypatch.setattr(recovery, "download_lead_payload", fake_download)
    monkeypatch.setattr(recovery, "extract_anchor_temperatures", fake_extract)
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)
    result = recovery._recover_available_lead(
        recovery.validate_issue_date("2022-01-01"), 24, tmp_path
    )
    assert attempts["count"] == 2
    assert result["rows"] == [{"anchor_id": "ok"}]
    assert result["resumed"] is False


def test_recover_available_lead_retries_corrupt_netcdf_keyerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery = _load_module()
    attempts = {"count": 0}

    def fake_download(day, lead_hours, destination, *, retries):
        attempts["count"] += 1
        destination.write_text(f"attempt-{attempts['count']}", encoding="utf-8")
        return {"status": "available", "payload": destination, "lead_hours": lead_hours}

    def fake_extract(payload_path, *, issue_date, lead_hours):
        if attempts["count"] == 1:
            raise KeyError(b"corrupt NetCDF typecode")
        return [{"anchor_id": "ok"}]

    monkeypatch.setattr(recovery, "download_lead_payload", fake_download)
    monkeypatch.setattr(recovery, "extract_anchor_temperatures", fake_extract)
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)
    result = recovery._recover_available_lead(
        recovery.validate_issue_date("2016-01-08"), 24, tmp_path
    )
    assert attempts["count"] == 2
    assert result["rows"] == [{"anchor_id": "ok"}]


def test_recover_available_lead_retries_corrupt_netcdf_indexerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery = _load_module()
    attempts = {"count": 0}

    def fake_download(day, lead_hours, destination, *, retries):
        attempts["count"] += 1
        destination.write_text(f"attempt-{attempts['count']}", encoding="utf-8")
        return {"status": "available", "payload": destination, "lead_hours": lead_hours}

    def fake_extract(payload_path, *, issue_date, lead_hours):
        if attempts["count"] == 1:
            raise IndexError("truncated NetCDF attribute buffer")
        return [{"anchor_id": "ok"}]

    monkeypatch.setattr(recovery, "download_lead_payload", fake_download)
    monkeypatch.setattr(recovery, "extract_anchor_temperatures", fake_extract)
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)
    result = recovery._recover_available_lead(
        recovery.validate_issue_date("2019-01-07"), 24, tmp_path
    )
    assert attempts["count"] == 2
    assert result["rows"] == [{"anchor_id": "ok"}]


def test_fetch_catalog_retries_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    recovery = _load_module()
    attempts = {"count": 0}

    class Response:
        content = b"catalog"

        def raise_for_status(self) -> None:
            return None

    class Session:
        def get(self, url, *, timeout):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise recovery.requests.ConnectTimeout("catalog timeout")
            return Response()

    monkeypatch.setattr(recovery, "_session", lambda: Session())
    monkeypatch.setattr(recovery, "_catalog_entries", lambda _: ("20220507", {24: {}}))
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)
    result = recovery.fetch_catalog("2022-05-07", retries=2)
    assert attempts["count"] == 2
    assert 24 in result["entries"]



def test_power_weather_runner_revalidates_current_miso_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_power_module()
    miso_root = tmp_path / "miso"
    expected_rows: list[dict[str, str]] = []
    observed_rows: list[dict[str, str]] = []
    for index in range(144):
        snapshot_id = f"snapshot-{index:03d}"
        month_dir = miso_root / "miso_rf_al" / snapshot_id
        month_dir.mkdir(parents=True)
        files = {
            "archive_zip_sha256": month_dir / "archive.zip",
            "power_features_sha256": month_dir / "power_features.csv",
            "excluded_members_sha256": month_dir / "excluded_members.json",
        }
        row = {"snapshot_id": snapshot_id}
        for key, path in files.items():
            path.write_bytes(f"{snapshot_id}:{key}".encode())
            row[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        expected_rows.append(dict(row))
        observed_rows.append(dict(row))
    source_audit = tmp_path / "source-audit.json"
    source_audit.write_text(json.dumps({"monthly_manifests": expected_rows}), encoding="utf-8")
    monkeypatch.setattr(runner, "MISO", miso_root)
    monkeypatch.setattr(runner, "MISO_SOURCE_AUDIT", source_audit)
    validation = {"verified_month_hash_records_sha256": runner.canonical_sha(observed_rows)}
    assert runner.verify_current_miso_identity(validation) == runner.canonical_sha(observed_rows)

    (miso_root / "miso_rf_al" / "snapshot-000" / "power_features.csv").write_text(
        "changed", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="power_features_sha256 changed"):
        runner.verify_current_miso_identity(validation)


def test_power_weather_runner_rejects_preregistered_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_power_module()
    paths = {
        "plan": tmp_path / "plan.json",
        "search": tmp_path / "search.json",
        "weather_contract": tmp_path / "weather-contract.json",
        "power": tmp_path / "power.json",
        "miso_source": tmp_path / "miso-source.json",
        "weather_result": tmp_path / "weather-result.json",
        "miso_validation": tmp_path / "miso-validation.json",
    }
    for key in ("search", "weather_contract", "power", "miso_source"):
        paths[key].write_text(json.dumps({"identity": key}), encoding="utf-8")
    fixed = {
        "issue426_search_plan_sha256": runner.sha256_file(paths["search"]),
        "issue426_weather_contract_sha256": runner.sha256_file(paths["weather_contract"]),
        "issue452_power_result_sha256": runner.sha256_file(paths["power"]),
        "issue452_miso_capture_audit_sha256": runner.sha256_file(paths["miso_source"]),
    }
    paths["plan"].write_text(
        json.dumps({"fixed_authorities": fixed, "protected_confirmation_accessed": False}),
        encoding="utf-8",
    )
    paths["weather_result"].write_text(
        json.dumps(
            {
                "dataset_frozen": True,
                "complete": True,
                "pit_safe": True,
                "protected_confirmation_accessed": False,
                "successor_plan_sha256": runner.sha256_file(paths["plan"]),
            }
        ),
        encoding="utf-8",
    )
    paths["miso_validation"].write_text(
        json.dumps(
            {
                "all_archive_and_feature_hashes_match_issue452": True,
                "audit": {
                    "research_pit_ready": True,
                    "usable_day_count": 4374,
                    "excluded_member_count": 9,
                },
                "tracked_issue452_capture_audit_sha256": runner.sha256_file(paths["miso_source"]),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "PLAN", paths["plan"])
    monkeypatch.setattr(runner, "SEARCH_PLAN", paths["search"])
    monkeypatch.setattr(runner, "WEATHER_CONTRACT", paths["weather_contract"])
    monkeypatch.setattr(runner, "POWER_RESULT", paths["power"])
    monkeypatch.setattr(runner, "MISO_SOURCE_AUDIT", paths["miso_source"])
    monkeypatch.setattr(runner, "WEATHER_RESULT", paths["weather_result"])
    monkeypatch.setattr(runner, "MISO_VALIDATION", paths["miso_validation"])
    monkeypatch.setattr(runner, "verify_current_miso_identity", lambda _: "identity")
    _, _, _, identity = runner.validate_authority()
    assert identity == "identity"

    paths["power"].write_text(json.dumps({"identity": "changed"}), encoding="utf-8")
    with pytest.raises(
        RuntimeError,
        match="preregistered authority identity changed: issue452_power_result_sha256",
    ):
        runner.validate_authority()
