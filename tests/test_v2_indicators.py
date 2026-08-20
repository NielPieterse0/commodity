from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import commodity.v2_indicator_contract as indicator_contract
import commodity.v2_indicator_market as indicator_market
import commodity.v2_indicator_weather_storage as indicator_weather_storage
from commodity.v2_indicator_weather_storage import (
    _build_weather_revision_from_verified_rows,
)
from commodity.v2_indicators import (
    ALL_INCREMENT_FEATURES,
    ATTRIBUTION_VARIANTS,
    CANDIDATE_ID,
    FAMILIES,
    FEATURES_BY_FAMILY,
    PRIMARY_VARIANT,
    SOURCE_POLICY_SHA256,
    SPEC_PATH,
    SPEC_REVISION,
    IndicatorContractError,
    bind_activation_contract,
    build_curve_increments,
    build_lineage_handoff,
    build_positioning_increments,
    build_power_increments,
    build_storage_increment,
    build_storage_public_value_events,
    build_variant_matrix,
    build_volatility_increment,
    build_weather_revision,
    canonical_sha256,
    dataframe_sha256,
    parse_pinned_source_policy,
    read_frozen_multiplicity_manifest,
    require_empirical_release,
    validate_preprocessing_plan,
    validate_required_coverage,
    variant_role,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def source_policy():
    raw = (ROOT / "config" / "data_sources.json").read_bytes()
    policy = parse_pinned_source_policy(raw)
    assert policy.sha256 == SOURCE_POLICY_SHA256
    return policy


@pytest.fixture(scope="module")
def activation_binding():
    contract = json.loads(
        (
            ROOT
            / "docs"
            / "development"
            / "v2-activation-preregistration"
            / "activation-contract.json"
        ).read_text(encoding="utf-8")
    )
    candidates = json.loads(
        (ROOT / "config" / "experiment_candidates.json").read_text(encoding="utf-8")
    )
    return bind_activation_contract(
        contract,
        candidates,
        read_frozen_multiplicity_manifest(ROOT),
    )


def _contract_normalized_source_manifest(binding: dict) -> dict:
    implementation = binding["implementation_revision"]
    files = {}
    for relative in implementation["source_manifest_paths"]:
        raw = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        files[relative] = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "files": files,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def _prospective_current_source_binding() -> tuple[dict, dict]:
    contract = json.loads(
        (ROOT / "docs/development/v2-activation-preregistration/activation-contract.json").read_text(
            encoding="utf-8"
        )
    )
    candidates = json.loads(
        (ROOT / "config/experiment_candidates.json").read_text(encoding="utf-8")
    )
    candidate = candidates["candidates"][CANDIDATE_ID]
    candidate["preparation_revision"] = {
        "pr": 98,
        "head": SPEC_REVISION,
        "path": SPEC_PATH,
    }
    current = candidate["implementation_revision"]
    current["source_manifest_paths"] = list(indicator_contract.IMPLEMENTATION_SOURCE_PATHS)
    manifest = _contract_normalized_source_manifest({"implementation_revision": current})
    current["source_manifest_sha256"] = manifest["manifest_sha256"]
    binding = bind_activation_contract(
        contract,
        candidates,
        read_frozen_multiplicity_manifest(ROOT),
    )
    return binding, manifest


def test_repository_bindings_are_exact_and_empirical_execution_is_released(
    source_policy, activation_binding
) -> None:
    assert source_policy.sha256 == SOURCE_POLICY_SHA256
    assert activation_binding["candidate_id"] == CANDIDATE_ID
    assert activation_binding["preparation_revision"] == {
        "head": SPEC_REVISION,
        "path": SPEC_PATH,
    }
    require_empirical_release(activation_binding)


def test_activation_binding_hash_detects_tampering(activation_binding) -> None:
    tampered = json.loads(json.dumps(activation_binding))
    tampered["artifact_namespace"] = "artifacts/not-83/"
    with pytest.raises(IndicatorContractError, match="binding hash"):
        require_empirical_release(tampered)


def _weather_rows(policy):
    cfg = policy.payload["sources"]["weather"]
    anchors = [str(item["id"]) for item in cfg["v1_anchors"]]
    lead_start, lead_end = [int(value) for value in cfg["v1_feature_lead_hours"]]
    base = float(cfg["v1_degree_day_base_c"])
    cycle = int(cfg["v1_run_cycle_utc_hour"])
    current = pd.Timestamp("2026-01-02T00:00Z") + pd.Timedelta(hours=cycle)
    prior = current - pd.Timedelta(days=1)
    valid = pd.date_range(
        current + pd.Timedelta(hours=lead_start),
        current + pd.Timedelta(hours=lead_end),
        freq="h",
        inclusive="left",
    )
    source_id = cfg["accepted_source_ids"][0]
    rows = []
    for run_id, issued_at, temperature in (
        ("prior", prior, base - 9.0),
        ("current", current, base - 8.0),
    ):
        for anchor in anchors:
            for valid_at in valid:
                rows.append(
                    {
                        "run_id": run_id,
                        "issued_at": issued_at,
                        "available_at": issued_at + pd.Timedelta(hours=1),
                        "anchor_id": anchor,
                        "forecast_valid_at": valid_at,
                        "temperature_2m": temperature,
                        "revision_status": "issued_run_immutable",
                        "source_id": source_id,
                    }
                )
    return pd.DataFrame(rows), current + pd.Timedelta(hours=2)


def test_weather_revision_uses_same_valid_window(source_policy) -> None:
    rows, cutoff = _weather_rows(source_policy)
    result = _build_weather_revision_from_verified_rows(rows, cutoff, source_policy)
    assert result == pytest.approx(
        {
            "weather_hdd65_revision_1run": -7.0,
            "weather_cdd65_revision_1run": 0.0,
        }
    )


def test_weather_revision_fails_on_missing_or_tied_predecessor(source_policy) -> None:
    rows, cutoff = _weather_rows(source_policy)
    prior_index = rows.index[rows["run_id"].eq("prior")][0]
    with pytest.raises(IndicatorContractError, match="exact current valid-time window"):
        _build_weather_revision_from_verified_rows(
            rows.drop(index=prior_index), cutoff, source_policy
        )
    duplicate = rows.loc[rows["run_id"].eq("current")].copy()
    duplicate["run_id"] = "duplicate-current"
    with pytest.raises(IndicatorContractError, match="duplicate/tied"):
        _build_weather_revision_from_verified_rows(
            pd.concat([rows, duplicate], ignore_index=True), cutoff, source_policy
        )


def _write_synthetic_weather_archive(root: Path, policy) -> tuple[pd.Timestamp, str, Path]:
    cfg = policy.payload["sources"]["weather"]
    anchors = [str(item["id"]) for item in cfg["v1_anchors"]]
    lead_start, lead_end = [int(value) for value in cfg["v1_feature_lead_hours"]]
    base = float(cfg["v1_degree_day_base_c"])
    source_id = cfg["accepted_source_ids"][0]
    current = pd.Timestamp("2026-01-02T00:00Z")
    prior = current - pd.Timedelta(days=1)
    valid_times = pd.date_range(
        current + pd.Timedelta(hours=lead_start),
        current + pd.Timedelta(hours=lead_end),
        freq="h",
        inclusive="left",
    )
    manifest_entries: list[dict[str, str]] = []
    tamper_path: Path | None = None
    for issued_at, temperature in ((prior, base - 9.0), (current, base - 8.0)):
        snapshot_id = issued_at.strftime("%Y%m%dT%H%MZ")
        run_dir = root / snapshot_id
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(parents=True)
        artifacts = []
        for anchor in anchors:
            payload = {
                "utc_offset_seconds": 0,
                "timezone": "GMT",
                "hourly": {
                    "time": [timestamp.strftime("%Y-%m-%dT%H:%M") for timestamp in valid_times],
                    "temperature_2m": [temperature] * len(valid_times),
                },
            }
            artifact_raw = json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            artifact_path = raw_dir / f"{anchor}.json"
            artifact_path.write_bytes(artifact_raw)
            artifacts.append(
                {
                    "path": f"raw/{anchor}.json",
                    "sha256": hashlib.sha256(artifact_raw).hexdigest(),
                }
            )
            if issued_at == current and anchor == anchors[0]:
                tamper_path = artifact_path
        manifest = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "source_id": source_id,
            "model": cfg["model"],
            "issued_at": issued_at.isoformat(),
            "available_at": (issued_at + pd.Timedelta(hours=1)).isoformat(),
            "revision_status": "issued_run_immutable",
            "artifacts": artifacts,
        }
        manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_bytes(manifest_raw)
        normalized = manifest_raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        manifest_entries.append(
            {
                "path": manifest_path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(normalized).hexdigest(),
            }
        )
    assert tamper_path is not None
    archive_digest = canonical_sha256(
        {"schema_version": 1, "manifests": manifest_entries}
    )
    return current + pd.Timedelta(hours=2), archive_digest, tamper_path


def test_weather_archive_production_pins_are_immutable() -> None:
    assert indicator_weather_storage.FROZEN_WEATHER_ARCHIVE_RUNS == 723
    assert indicator_weather_storage.FROZEN_WEATHER_ARCHIVE_MANIFEST_SHA256 == (
        "44e2ed4c7206ecde8dad442d6dfc70b4e14387c97621a4b516846a0266329096"
    )


def test_weather_archive_rejects_missing_extra_or_substituted_manifests(
    source_policy, tmp_path, monkeypatch
) -> None:
    missing_root = tmp_path / "missing"
    _, archive_digest, missing_artifact = _write_synthetic_weather_archive(
        missing_root, source_policy
    )
    monkeypatch.setattr(indicator_weather_storage, "FROZEN_WEATHER_ARCHIVE_RUNS", 2)
    monkeypatch.setattr(
        indicator_weather_storage,
        "FROZEN_WEATHER_ARCHIVE_MANIFEST_SHA256",
        archive_digest,
    )
    (missing_artifact.parent.parent.parent / "20260101T0000Z" / "manifest.json").unlink()
    with pytest.raises(IndicatorContractError, match="run-manifest count"):
        build_weather_revision(missing_root, "2026-01-02T02:00Z", source_policy)

    extra_root = tmp_path / "extra"
    _write_synthetic_weather_archive(extra_root, source_policy)
    extra_manifest = extra_root / "20990101T0000Z" / "manifest.json"
    extra_manifest.parent.mkdir(parents=True)
    extra_manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(IndicatorContractError, match="run-manifest count"):
        build_weather_revision(extra_root, "2026-01-02T02:00Z", source_policy)

    substituted_root = tmp_path / "substituted"
    _, _, substituted_artifact = _write_synthetic_weather_archive(
        substituted_root, source_policy
    )
    manifest_path = substituted_artifact.parent.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["available_at"] = "2026-01-02T01:01:00+00:00"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(IndicatorContractError, match="archive manifests differ"):
        build_weather_revision(substituted_root, "2026-01-02T02:00Z", source_policy)


def test_weather_revision_verifies_frozen_archive_and_raw_artifacts(
    source_policy, tmp_path, monkeypatch
) -> None:
    cutoff, archive_digest, tamper_path = _write_synthetic_weather_archive(
        tmp_path, source_policy
    )
    monkeypatch.setattr(indicator_weather_storage, "FROZEN_WEATHER_ARCHIVE_RUNS", 2)
    monkeypatch.setattr(
        indicator_weather_storage,
        "FROZEN_WEATHER_ARCHIVE_MANIFEST_SHA256",
        archive_digest,
    )
    result = build_weather_revision(tmp_path, cutoff, source_policy)
    assert result == pytest.approx(
        {
            "weather_hdd65_revision_1run": -7.0,
            "weather_cdd65_revision_1run": 0.0,
        }
    )

    tamper_path.write_bytes(tamper_path.read_bytes() + b" ")
    with pytest.raises(IndicatorContractError, match="differs from its run manifest"):
        build_weather_revision(tmp_path, cutoff, source_policy)


def test_storage_public_state_preserves_revision_timing(source_policy) -> None:
    history = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2025-01-03T00:00Z", "2025-01-10T00:00Z", "2025-01-17T00:00Z"]
            ),
            "storage_lower48_bcf": [100.0, 113.0, 130.0],
        }
    )
    revisions = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-01-10T00:00Z"]),
            "original_storage_lower48_bcf": [110.0],
            "revised_storage_lower48_bcf": [113.0],
            "revision_date": ["2025-01-16T23:30:00-05:00"],
        }
    )
    events = build_storage_public_value_events(history, revisions, source_policy)
    week = pd.Timestamp("2025-01-10T00:00Z")
    values = events.loc[events["observed_for"].eq(week)].sort_values("available_at")
    assert values["storage_lower48_bcf"].tolist() == [110.0, 113.0]
    assert values["revision_status"].eq("point_in_time").all()
    assert values.iloc[-1]["available_at"] == pd.Timestamp("2025-01-17T04:59:00Z")
    assert values.iloc[-1]["availability_basis"] == "revision_date_2359_local_conservative"


def test_storage_ordinary_revision_is_hidden_until_exact_reconstructed_cutoff(
    source_policy,
) -> None:
    history = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2024-12-20T00:00Z", "2024-12-27T00:00Z", "2025-01-03T00:00Z"]
            ),
            "storage_lower48_bcf": [100.0, 110.0, 123.0],
        }
    )
    revisions = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-01-03T00:00Z"]),
            "original_storage_lower48_bcf": [120.0],
            "revised_storage_lower48_bcf": [123.0],
            "revision_date": ["2025-01-16T23:30:00-05:00"],
        }
    )
    events = build_storage_public_value_events(history, revisions, source_policy)
    before = build_storage_increment(events, "2025-01-17T04:58:59Z", source_policy)
    at_cutoff = build_storage_increment(events, "2025-01-17T04:59:00Z", source_policy)
    assert before["storage_change_accel_bcf"] == pytest.approx(0.0)
    assert at_cutoff["storage_change_accel_bcf"] == pytest.approx(3.0)


def test_storage_special_revision_event_has_exact_pit_boundary_and_timezone(
    source_policy,
) -> None:
    history = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2024-10-25T00:00Z", "2024-11-01T00:00Z", "2024-11-08T00:00Z"]
            ),
            "storage_lower48_bcf": [100.0, 110.0, 123.0],
        }
    )
    revisions = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2024-11-08T00:00Z"]),
            "original_storage_lower48_bcf": [120.0],
            "revised_storage_lower48_bcf": [123.0],
            "revision_date": ["2024-11-18T12:00:00-05:00"],
        }
    )
    events = build_storage_public_value_events(history, revisions, source_policy)
    special = events.loc[events["availability_basis"].eq("special_revision_event")]
    assert len(special) == 1
    assert special.iloc[0]["available_at"] == pd.Timestamp("2024-11-18T20:00:00Z")
    before = build_storage_increment(events, "2024-11-18T19:59:59Z", source_policy)
    at_cutoff = build_storage_increment(events, "2024-11-18T20:00:00Z", source_policy)
    assert before["storage_change_accel_bcf"] == pytest.approx(0.0)
    assert at_cutoff["storage_change_accel_bcf"] == pytest.approx(3.0)

    bad_payload = json.loads(json.dumps(source_policy.payload))
    bad_payload["sources"]["eia_storage"]["availability_policy"][
        "special_revision_events"
    ]["2024_sample_reselection"] = "2024-11-18T15:00:00"
    bad_policy = type(source_policy)(payload=bad_payload)
    with pytest.raises(IndicatorContractError, match="timezone-aware"):
        build_storage_public_value_events(history, revisions, bad_policy)


def test_storage_acceleration_uses_latest_public_values(source_policy) -> None:
    source_id = source_policy.payload["sources"]["eia_storage"]["accepted_source_ids"][0]
    events = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                [
                    "2026-01-01T00:00Z",
                    "2026-01-08T00:00Z",
                    "2026-01-08T00:00Z",
                    "2026-01-15T00:00Z",
                ]
            ),
            "available_at": pd.to_datetime(
                [
                    "2026-01-02T15:30Z",
                    "2026-01-09T15:30Z",
                    "2026-01-10T15:30Z",
                    "2026-01-16T15:30Z",
                ]
            ),
            "storage_lower48_bcf": [100.0, 110.0, 112.0, 130.0],
            "revision_status": ["point_in_time"] * 4,
            "source_id": [source_id] * 4,
        }
    )
    result = build_storage_increment(events, "2026-01-17T00:00Z", source_policy)
    assert result["storage_change_accel_bcf"] == pytest.approx(6.0)


def test_storage_staleness_fails_closed(source_policy) -> None:
    source_id = source_policy.payload["sources"]["eia_storage"]["accepted_source_ids"][0]
    events = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2025-12-01T00:00Z", "2025-12-08T00:00Z", "2025-12-15T00:00Z"]
            ),
            "available_at": pd.to_datetime(
                ["2025-12-02T00:00Z", "2025-12-09T00:00Z", "2025-12-16T00:00Z"]
            ),
            "storage_lower48_bcf": [100.0, 110.0, 120.0],
            "revision_status": ["point_in_time"] * 3,
            "source_id": [source_id] * 3,
        }
    )
    with pytest.raises(IndicatorContractError, match="staleness"):
        build_storage_increment(events, "2026-01-17T00:00Z", source_policy)


def test_curve_increments_require_exact_frozen_dataset_artifact(
    source_policy, activation_binding, tmp_path, monkeypatch
) -> None:
    rows = pd.DataFrame(
        {
            "prediction_time": ["2026-01-02T23:59:00Z", "2026-01-05T23:59:00Z"],
            "curve_spread_m1_m2": [1.0, 1.5],
            "curve_spread_m2_m3": [0.5, 0.75],
            "curve_slope_m1_m4": [2.0, 3.0],
        }
    )
    dataset_path = tmp_path / "dataset.csv"
    rows.to_csv(dataset_path, index=False, lineterminator="\n")
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    frozen_context = dict(indicator_market.FROZEN_MARKET_CONTEXT)
    frozen_context["dataset_sha256"] = digest
    monkeypatch.setattr(indicator_market, "FROZEN_MARKET_CONTEXT", frozen_context)
    binding = json.loads(json.dumps(activation_binding))
    binding["frozen_v1_control"]["context_identity"]["dataset_sha256"] = digest
    binding.pop("binding_sha256")
    binding["binding_sha256"] = canonical_sha256(binding)

    result = build_curve_increments(
        dataset_path,
        current_trade_date="2026-01-05",
        prediction_time="2026-01-06T00:00Z",
        session_sequence=["2026-01-02", "2026-01-05"],
        source_policy=source_policy,
        activation_binding=binding,
    )
    assert result == pytest.approx(
        {
            "curve_curvature_123": 0.75,
            "curve_spread_m1_m2_change_1": 0.5,
            "curve_slope_m1_m4_change_1": 1.0,
        }
    )

    dataset_path.write_text(dataset_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(IndicatorContractError, match="frozen #81 dataset"):
        build_curve_increments(
            dataset_path,
            current_trade_date="2026-01-05",
            prediction_time="2026-01-06T00:00Z",
            session_sequence=["2026-01-02", "2026-01-05"],
            source_policy=source_policy,
            activation_binding=binding,
        )


def test_curve_frozen_artifact_requires_immediate_prior_session(
    source_policy, activation_binding, tmp_path, monkeypatch
) -> None:
    rows = pd.DataFrame(
        {
            "prediction_time": ["2026-01-05T23:59:00Z"],
            "curve_spread_m1_m2": [1.5],
            "curve_spread_m2_m3": [0.75],
            "curve_slope_m1_m4": [3.0],
        }
    )
    dataset_path = tmp_path / "missing-prior.csv"
    rows.to_csv(dataset_path, index=False, lineterminator="\n")
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    frozen_context = dict(indicator_market.FROZEN_MARKET_CONTEXT)
    frozen_context["dataset_sha256"] = digest
    monkeypatch.setattr(indicator_market, "FROZEN_MARKET_CONTEXT", frozen_context)
    binding = json.loads(json.dumps(activation_binding))
    binding["frozen_v1_control"]["context_identity"]["dataset_sha256"] = digest
    binding.pop("binding_sha256")
    binding["binding_sha256"] = canonical_sha256(binding)

    with pytest.raises(IndicatorContractError, match="prior session"):
        build_curve_increments(
            dataset_path,
            current_trade_date="2026-01-05",
            prediction_time="2026-01-06T00:00Z",
            session_sequence=["2026-01-02", "2026-01-05"],
            source_policy=source_policy,
            activation_binding=binding,
        )


def test_curve_legacy_dataframe_api_fails_closed_with_governance_error() -> None:
    legacy_rows = pd.DataFrame(
        {
            "trade_date": ["2026-01-02", "2026-01-05"],
            "available_at": ["2026-01-02T23:59:00Z", "2026-01-05T23:59:00Z"],
            "curve_spread_m1_m2": [1.0, 1.5],
            "curve_spread_m2_m3": [0.5, 0.75],
            "curve_slope_m1_m4": [2.0, 3.0],
        }
    )
    with pytest.raises(IndicatorContractError, match="legacy DataFrame curve input"):
        build_curve_increments(
            legacy_rows,
            current_trade_date="2026-01-05",
            prediction_time="2026-01-06T00:00Z",
            session_sequence=["2026-01-02", "2026-01-05"],
        )


def test_volatility_uses_same_contract_returns_across_roll() -> None:
    dates = pd.date_range("2026-01-01", periods=25, tz="UTC")
    rows: list[dict[str, object]] = []
    selected: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for contract, expiry, price in (
            ("NGF26", "2026-02-25", 3.0 + 0.01 * i),
            ("NGG26", "2026-03-25", 10.0 + 0.02 * i),
        ):
            rows.append(
                {
                    "trade_date": date,
                    "contract_id": contract,
                    "expiration": pd.Timestamp(expiry, tz="UTC"),
                    "available_at": date + pd.Timedelta(hours=23),
                    "settle": price,
                }
            )
        contract = "NGF26" if i < 20 else "NGG26"
        expiry = "2026-02-25" if i < 20 else "2026-03-25"
        selected.append(
            {
                "trade_date": date,
                "contract_id": contract,
                "expiration": pd.Timestamp(expiry, tz="UTC"),
                "available_at": date + pd.Timedelta(hours=23),
                "roll_reason": "prior_session_volume_crossover" if i == 20 else "hold",
            }
        )

    raw = pd.DataFrame(rows)
    path = pd.DataFrame(selected)
    result = indicator_market.build_roll_safe_volatility_features(
        raw, path, current_trade_date=dates[-1]
    )
    expected_returns = []
    for i in range(5, 25):
        if i < 20:
            expected_returns.append(np.log((3.0 + 0.01 * i) / (3.0 + 0.01 * (i - 1))))
        else:
            expected_returns.append(np.log((10.0 + 0.02 * i) / (10.0 + 0.02 * (i - 1))))
    expected = pd.Series(expected_returns, dtype=float)
    assert result["vol_20"] == pytest.approx(expected.std(ddof=1))
    assert result["vol_5"] == pytest.approx(expected.iloc[-5:].std(ddof=1))
    assert result["vol_ratio_5_20"] == pytest.approx(
        expected.iloc[-5:].std(ddof=1) / expected.std(ddof=1)
    )
    assert build_volatility_increment(
        raw, path, current_trade_date=dates[-1]
    ) == {"vol_ratio_5_20": pytest.approx(result["vol_ratio_5_20"])}
    with pytest.raises(IndicatorContractError, match="legacy inherited"):
        build_volatility_increment({"vol_5": 0.2, "vol_20": 0.1})
    with pytest.raises(IndicatorContractError, match="requires 20 selected sessions"):
        indicator_market.build_roll_safe_volatility_features(
            raw.loc[raw["trade_date"] <= dates[9]],
            path.iloc[:10],
            current_trade_date=dates[9],
        )


def test_positioning_uses_distinct_pit_reports(source_policy) -> None:
    source_id = source_policy.payload["sources"]["cftc_cot"]["accepted_source_ids"][0]
    reports = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2026-01-06T00:00Z", "2026-01-13T00:00Z"]
            ),
            "available_at": pd.to_datetime(
                ["2026-01-09T23:59Z", "2026-01-16T23:59Z"]
            ),
            "managed_money_long_pct_oi": [0.40, 0.50],
            "managed_money_short_pct_oi": [0.30, 0.25],
            "revision_status": ["point_in_time", "point_in_time"],
            "source_id": [source_id, source_id],
        }
    )
    assert build_positioning_increments(
        reports, "2026-01-17T00:00Z", source_policy
    ) == pytest.approx(
        {
            "managed_money_net_pct_oi": 0.25,
            "managed_money_net_pct_oi_change_1report": 0.15,
        }
    )
    reports.loc[0, "revision_status"] = "current_snapshot_revised_history"
    with pytest.raises(IndicatorContractError, match="point-in-time"):
        build_positioning_increments(reports, "2026-01-17T00:00Z", source_policy)


def test_power_change_is_shifted_valid_day(source_policy) -> None:
    source_id = source_policy.payload["sources"]["nyiso_load_forecast"][
        "accepted_source_ids"
    ][0]
    forecasts = pd.DataFrame(
        {
            "issued_at": pd.to_datetime(
                ["2026-01-01T17:00Z", "2026-01-02T17:00Z"]
            ),
            "available_at": pd.to_datetime(
                ["2026-01-01T17:05Z", "2026-01-02T17:05Z"]
            ),
            "forecast_valid_at": pd.to_datetime(
                ["2026-01-02T05:00Z", "2026-01-03T05:00Z"]
            ),
            "power_next_day_load_mean_mw": [100.0, 110.0],
            "power_next_day_load_max_mw": [120.0, 135.0],
            "power_next_day_load_min_mw": [90.0, 95.0],
            "revision_status": ["issued_run_immutable", "issued_run_immutable"],
            "source_id": [source_id, source_id],
        }
    )
    assert build_power_increments(
        forecasts, "2026-01-02T18:00Z", source_policy
    ) == pytest.approx(
        {
            "power_next_day_load_range_mw": 40.0,
            "power_next_day_load_mean_change_1run_mw": 10.0,
        }
    )
    forecasts.loc[0, "forecast_valid_at"] = pd.Timestamp("2025-12-31T05:00Z")
    with pytest.raises(IndicatorContractError, match="consecutive"):
        build_power_increments(forecasts, "2026-01-02T18:00Z", source_policy)


def _increments(rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            feature: np.arange(1, rows + 1, dtype=float)
            for feature in ALL_INCREMENT_FEATURES
        }
    )


def test_i_all_is_primary_and_i_no_variants_are_non_rescuing() -> None:
    increments = _increments()
    inherited = pd.DataFrame({"ret_1": [0.1, 0.2]}, index=increments.index)
    status = {family: True for family in FAMILIES}
    primary = build_variant_matrix(
        inherited, increments, variant=PRIMARY_VARIANT, family_status=status
    )
    assert primary.attrs["variant_role"] == "primary"
    assert primary.attrs["can_promote"] is True
    attribution = build_variant_matrix(
        inherited, increments, variant="I-NO-W", family_status=status
    )
    assert attribution.attrs["variant_role"] == "attribution_only"
    assert attribution.attrs["can_promote"] is False
    assert not set(FEATURES_BY_FAMILY["W"]).intersection(attribution.columns)
    assert variant_role("I-NO-W") == "attribution_only"
    assert tuple(ATTRIBUTION_VARIANTS) == (
        "I-NO-W",
        "I-NO-S",
        "I-NO-C",
        "I-NO-V",
        "I-NO-P",
        "I-NO-L",
    )
    status["W"] = False
    with pytest.raises(IndicatorContractError, match="I-ALL is invalid"):
        build_variant_matrix(
            inherited, increments, variant="I-NO-W", family_status=status
        )


def test_unlisted_variant_and_feature_are_rejected() -> None:
    increments = _increments()
    inherited = pd.DataFrame({"ret_1": [0.1, 0.2]}, index=increments.index)
    status = {family: True for family in FAMILIES}
    with pytest.raises(IndicatorContractError, match="unlisted"):
        build_variant_matrix(
            inherited, increments, variant="I-BEST-W", family_status=status
        )
    with pytest.raises(IndicatorContractError, match="frozen list"):
        build_variant_matrix(
            inherited,
            increments.assign(post_hoc_feature=1.0),
            variant=PRIMARY_VARIANT,
            family_status=status,
        )


def test_coverage_is_exactly_one_and_no_imputation_is_allowed() -> None:
    increments = _increments()
    assert validate_required_coverage(
        increments, fit_rows=[True, False], scored_rows=[False, True]
    ) == {
        "fit_rows_for_required_features": 1.0,
        "primary_scored_rows": 1.0,
    }
    broken = increments.copy()
    broken.loc[1, ALL_INCREMENT_FEATURES[0]] = np.nan
    with pytest.raises(IndicatorContractError, match="1.000 finite coverage"):
        validate_required_coverage(
            broken, fit_rows=[True, False], scored_rows=[False, True]
        )
    valid = {
        "fit_scope": "fold_train_only",
        "imputation": None,
        "clipping": None,
        "winsorization": None,
        "target_encoding": None,
        "learned_feature_selection": None,
    }
    assert validate_preprocessing_plan(valid) == valid
    with pytest.raises(IndicatorContractError, match="fold_train_only"):
        validate_preprocessing_plan({**valid, "fit_scope": "whole_sample"})
    with pytest.raises(IndicatorContractError, match="prohibited"):
        validate_preprocessing_plan({**valid, "imputation": "median"})


def test_hashes_and_lineage_handoff_are_deterministic() -> None:
    activation_binding, runtime_manifest = _prospective_current_source_binding()
    increments = _increments()
    input_frame = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-01-01T00:00Z", "2026-01-02T00:00Z"]
            ),
            "source_id": ["synthetic", "synthetic"],
        }
    )
    assert dataframe_sha256(increments) == dataframe_sha256(increments.copy())
    handoff = build_lineage_handoff(
        binding=activation_binding,
        input_frame=input_frame,
        feature_frame=increments,
        implementation_config={"fit_scope": "fold_train_only"},
        implementation_revision="a" * 40,
        runtime_source_manifest=runtime_manifest,
    )
    identity = handoff.pop("artifact_identity_sha256")
    assert handoff["candidate_id"] == CANDIDATE_ID
    assert identity == canonical_sha256(handoff)
    with pytest.raises(IndicatorContractError, match="exact 40-hex"):
        build_lineage_handoff(
            binding=activation_binding,
            input_frame=input_frame,
            feature_frame=increments,
            implementation_config={"fit_scope": "fold_train_only"},
            implementation_revision="not-a-sha",
        )