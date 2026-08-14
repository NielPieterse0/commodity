import numpy as np
import pandas as pd
import pytest


def _market_frame(n: int = 80) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = 3.0 + np.linspace(0.0, 0.8, n) + 0.05 * np.sin(np.arange(n))
    return pd.DataFrame(
        {
            "open": close - 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1000.0 + np.arange(n),
        },
        index=index,
    )


def test_pit_dataset_identity_is_deterministic() -> None:
    from commodity.research_dataset import build_pit_dataset

    first, first_manifest = build_pit_dataset(_market_frame())
    second, second_manifest = build_pit_dataset(_market_frame())

    pd.testing.assert_frame_equal(first, second)
    assert first_manifest["dataset_sha256"] == second_manifest["dataset_sha256"]
    assert first_manifest["dataset_id"] == second_manifest["dataset_id"]
    assert first_manifest["evidence_mode"] == "research_pit"
    assert first_manifest["completeness"] == "pit_core"


def test_screening_source_is_rejected_from_pit_dataset() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source = PitFeatureSource(
        name="revised_power",
        family="power",
        frame=pd.DataFrame(
            {
                "available_at": [pd.Timestamp("2025-02-01T12:00:00Z")],
                "availability_status": ["reconstructed_conservative"],
                "revision_status": ["current_snapshot_revised_history"],
                "power_signal": [1.0],
            }
        ),
        value_columns=("power_signal",),
        evidence_mode="screening",
    )

    with pytest.raises(ValueError):
        build_pit_dataset(_market_frame(), exogenous=[source])


def test_pit_join_respects_availability_cutoff() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source = PitFeatureSource(
        name="issued_weather",
        family="weather",
        frame=pd.DataFrame(
            {
                "available_at": [pd.Timestamp("2025-03-01T12:00:00Z")],
                "availability_status": ["reconstructed_conservative"],
                "revision_status": ["issued_run_immutable"],
                "weather_signal": [7.0],
            }
        ),
        value_columns=("weather_signal",),
    )
    dataset, _ = build_pit_dataset(_market_frame(), exogenous=[source])

    assert dataset.index.min() >= pd.Timestamp("2025-03-01T12:00:00Z")
    assert dataset["weather_signal"].eq(7.0).all()


def test_full_v1_requires_all_configured_families() -> None:
    from commodity.research_dataset import build_pit_dataset

    with pytest.raises(ValueError):
        build_pit_dataset(
            _market_frame(),
            required_families=("market", "calendar_seasonality", "weather"),
            require_full_v1=True,
        )


def test_full_v1_power_requires_configured_nyiso_source_identity() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    times = pd.date_range("2025-01-01T12:00:00Z", periods=80, freq="D")

    def power_source(source_id: str) -> PitFeatureSource:
        return PitFeatureSource(
            name="power_forecast",
            family="power",
            frame=pd.DataFrame(
                {
                    "issued_at": times - pd.Timedelta(days=1),
                    "available_at": times,
                    "availability_status": "reconstructed_conservative",
                    "revision_status": "issued_run_immutable",
                    "power_signal": 1.0,
                }
            ),
            value_columns=("power_signal",),
            source_id=source_id,
        )

    with pytest.raises(ValueError, match="power.*configured_power_source_identity_mismatch"):
        build_pit_dataset(
            _market_frame(),
            exogenous=[power_source("eia_api_v2")],
            required_families=("market", "calendar_seasonality", "power"),
            require_full_v1=True,
        )

    dataset, manifest = build_pit_dataset(
        _market_frame(),
        exogenous=[power_source("nyiso_p7_iso_load_forecast")],
        required_families=("market", "calendar_seasonality", "power"),
        require_full_v1=True,
    )
    assert not dataset.empty
    assert manifest["completeness"] == "full_v1"
    assert manifest["exogenous_family_audits"]["power"][0]["full_v1_ready"] is True


def test_full_v1_rejects_family_name_without_full_window_evidence() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source = PitFeatureSource(
        name="issued_weather",
        family="weather",
        frame=pd.DataFrame(
            {
                "issued_at": [pd.Timestamp("2025-03-01T00:00:00Z")],
                "available_at": [pd.Timestamp("2025-03-01T06:10:00Z")],
                "availability_status": ["reconstructed_conservative"],
                "revision_status": ["issued_run_immutable"],
                "weather_signal": [7.0],
            }
        ),
        value_columns=("weather_signal",),
    )
    with pytest.raises(ValueError, match="weather.*coverage_incomplete"):
        build_pit_dataset(
            _market_frame(),
            exogenous=[source],
            required_families=("market", "calendar_seasonality", "weather"),
            require_full_v1=True,
        )


def _canonical_contracts(n: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        front = 3.0 + i / 1000
        rows.extend(
            [
                {
                    "trade_date": date,
                    "contract_id": "NGZ26",
                    "expiration": pd.Timestamp("2026-12-28", tz="UTC"),
                    "settle": front,
                    "high": front + 0.05,
                    "low": front - 0.05,
                    "volume": 1000 + i,
                    "available_at": date + pd.Timedelta(hours=22),
                },
                {
                    "trade_date": date,
                    "contract_id": "NGF27",
                    "expiration": pd.Timestamp("2027-01-27", tz="UTC"),
                    "settle": front + 0.1,
                    "high": front + 0.15,
                    "low": front + 0.05,
                    "volume": 800 + i,
                    "available_at": date + pd.Timedelta(hours=22),
                },
            ]
        )
    return pd.DataFrame(rows)


def test_canonical_dataset_rejects_proxy_market_only() -> None:
    from commodity.research_dataset import build_pit_dataset

    with pytest.raises(ValueError, match="canonical contract"):
        build_pit_dataset(_market_frame(), evidence_mode="canonical")


def test_canonical_dataset_consumes_provider_neutral_contract_rows(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    from commodity.research_dataset import build_pit_dataset

    dataset, manifest = build_pit_dataset(
        None,
        evidence_mode="canonical",
        canonical_contracts=_canonical_contracts_four(),
    )
    assert not dataset.empty
    assert manifest["canonical_market_evidence"] is True
    assert manifest["market_input"] == "canonical_contracts"
    assert dataset.index.tz is not None


def _canonical_contracts_four() -> pd.DataFrame:
    base = _canonical_contracts()
    extras: list[dict[str, object]] = []
    for date, group in base.groupby("trade_date"):
        front = float(group.loc[group["contract_id"] == "NGZ26", "settle"].iloc[0])
        for contract, expiry, offset, volume in [
            ("NGG27", "2027-02-24", 0.2, 700.0),
            ("NGH27", "2027-03-29", 0.3, 600.0),
        ]:
            extras.append({
                "trade_date": date,
                "contract_id": contract,
                "expiration": pd.Timestamp(expiry, tz="UTC"),
                "settle": front + offset,
                "high": front + offset + 0.05,
                "low": front + offset - 0.05,
                "volume": volume,
                "available_at": date + pd.Timedelta(hours=22),
            })
    return pd.concat([base, pd.DataFrame(extras)], ignore_index=True)


def test_canonical_dataset_adds_market_structure_and_lineage(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    first, first_manifest = research_dataset.build_pit_dataset(
        None, evidence_mode="canonical", canonical_contracts=_canonical_contracts_four()
    )
    second, second_manifest = research_dataset.build_pit_dataset(
        None, evidence_mode="canonical", canonical_contracts=_canonical_contracts_four()
    )
    assert "market_structure" in first_manifest["included_feature_families"]
    assert "curve_spread_m1_m2" in first.columns
    assert "curve_slope_m1_m4" in first.columns
    lineage = first_manifest["market_structure"]
    assert lineage["synthetic_series_tradable"] is False
    for key in ["contract_input_sha256", "selected_path_sha256", "roll_ledger_sha256", "curve_features_sha256", "curve_audit_sha256", "roll_policy_sha256"]:
        assert len(lineage[key]) == 64
        assert lineage[key] == second_manifest["market_structure"][key]
    pd.testing.assert_frame_equal(first, second)


def _rolling_canonical_contracts() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dates = pd.date_range("2026-01-01", periods=40, freq="D", tz="UTC")
    specs = [
        ("NGG26", "2026-02-10", 0.0, 1000.0),
        ("NGH26", "2026-03-27", 0.1, 700.0),
        ("NGJ26", "2026-04-28", 0.2, 600.0),
        ("NGK26", "2026-05-27", 0.3, 500.0),
    ]
    for i, date in enumerate(dates):
        base = 3.0 + i / 1000
        for contract, expiry, offset, volume in specs:
            if date <= pd.Timestamp(expiry, tz="UTC"):
                rows.append({"trade_date": date, "contract_id": contract, "expiration": pd.Timestamp(expiry, tz="UTC"), "settle": base + offset, "high": base + offset + 0.05, "low": base + offset - 0.05, "volume": volume, "available_at": date + pd.Timedelta(hours=22)})
    return pd.DataFrame(rows)


def test_canonical_target_skips_cross_contract_roll_return(monkeypatch) -> None:
    from commodity import research_dataset
    from commodity.config import assumptions_config, data_config
    from commodity.rolls import build_derived_continuous_series

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    contracts = _rolling_canonical_contracts()
    policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    path, ledger = build_derived_continuous_series(
        contracts, data_config()["canonical_contract_schema"], policy
    )
    roll_date = ledger.iloc[0]["trade_date"]
    roll_position = path.index[path["trade_date"] == roll_date][0]
    predecessor_time = pd.Timestamp(path.iloc[roll_position - 1]["available_at"])
    dataset, _ = research_dataset.build_pit_dataset(
        None, evidence_mode="canonical", canonical_contracts=contracts
    )
    assert predecessor_time not in dataset.index


def test_canonical_dataset_reconstructs_configured_market_availability(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    contracts = _canonical_contracts_four().drop(columns=["available_at"])
    dataset, manifest = research_dataset.build_pit_dataset(
        None, evidence_mode="canonical", canonical_contracts=contracts
    )
    assert not dataset.empty
    assert (dataset.index.hour == 23).all()
    assert (dataset.index.minute == 59).all()
    assert manifest["market_structure"]["availability_status"] == "reconstructed_conservative"


def test_canonical_market_lineage_names_representation_semantics(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    _, manifest = research_dataset.build_pit_dataset(
        None, evidence_mode="canonical", canonical_contracts=_canonical_contracts_four()
    )
    assert manifest["market_structure"]["representation"] == {
        "status": "derived_only",
        "adjustment_method": "none_stored_raw",
        "authoritative_storage": "raw_per_contract",
        "exchange": "NYMEX",
        "product_code": "NG",
        "session_timezone": "America/New_York",
        "calendar": "CME_NYMEX",
    }
    assert len(manifest["market_structure"]["market_semantics_sha256"]) == 64


def test_canonical_dataset_fails_closed_without_required_curve_ranks(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    with pytest.raises(ValueError, match="M1-M4 market structure"):
        research_dataset.build_pit_dataset(
            None, evidence_mode="canonical", canonical_contracts=_canonical_contracts()
        )


def test_canonical_dataset_fails_closed_without_curve_volume_evidence(monkeypatch) -> None:
    from commodity import research_dataset

    monkeypatch.setattr(research_dataset, "assert_canonical_market_ready", lambda *_: None)
    contracts = _canonical_contracts_four()
    contracts["volume"] = float("nan")
    with pytest.raises(ValueError, match="complete M1-M4 market structure"):
        research_dataset.build_pit_dataset(
            None, evidence_mode="canonical", canonical_contracts=contracts
        )


def test_exogenous_manifest_binds_source_lineage_without_metadata_features() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source_frame = pd.DataFrame(
        {
            "issued_at": [pd.Timestamp("2025-03-01T00:00:00Z")],
            "available_at": [pd.Timestamp("2025-03-01T06:10:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["issued_run_immutable"],
            "availability_basis": ["open_meteo_global_model_delay"],
            "weather_signal": [7.0],
        }
    )
    source = PitFeatureSource(
        name="issued_weather",
        family="weather",
        frame=source_frame,
        value_columns=("weather_signal",),
        source_id="open_meteo_single_runs",
        source_vintage="2025-03-01T00:00:00Z",
    )
    first, first_manifest = build_pit_dataset(_market_frame(), exogenous=[source])
    second, second_manifest = build_pit_dataset(_market_frame(), exogenous=[source])
    lineage = first_manifest["exogenous_sources"][0]
    assert lineage["family"] == "weather"
    assert lineage["source_id"] == "open_meteo_single_runs"
    assert lineage["source_vintage"] == "2025-03-01T00:00:00Z"
    assert lineage["availability_statuses"] == ["reconstructed_conservative"]
    assert lineage["availability_bases"] == ["open_meteo_global_model_delay"]
    assert lineage["revision_statuses"] == ["issued_run_immutable"]
    assert lineage["input_rows"] > lineage["joined_rows"]
    assert lineage["unmatched_rows"] == lineage["input_rows"] - lineage["joined_rows"]
    assert 0.0 < lineage["join_coverage_ratio"] < 1.0
    assert len(lineage["source_sha256"]) == 64
    assert lineage == second_manifest["exogenous_sources"][0]
    assert "availability_status" not in first.columns
    assert "revision_status" not in first.columns
    pd.testing.assert_frame_equal(first, second)


def test_full_v1_keeps_all_audits_for_duplicate_required_family_sources() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    partial_times = pd.date_range("2025-02-01", "2025-03-21", freq="D", tz="UTC")
    full_times = pd.date_range("2025-01-20", "2025-03-21", freq="D", tz="UTC")

    def source(name: str, column: str, times: pd.DatetimeIndex) -> PitFeatureSource:
        return PitFeatureSource(
            name=name,
            family="weather",
            frame=pd.DataFrame(
                {
                    "issued_at": times,
                    "available_at": times,
                    "availability_status": "verified",
                    "revision_status": "issued_run_immutable",
                    column: 1.0,
                }
            ),
            value_columns=(column,),
        )

    with pytest.raises(ValueError, match="weather.*coverage_incomplete"):
        build_pit_dataset(
            _market_frame(),
            exogenous=[
                source("weather_partial", "weather_partial", partial_times),
                source("weather_full", "weather_full", full_times),
            ],
            required_families=("market", "calendar_seasonality", "weather"),
            require_full_v1=True,
        )


def test_evaluation_dataset_uses_contract_market_structure_without_promotion_rights() -> None:
    from commodity.research_dataset import build_pit_dataset

    dataset, manifest = build_pit_dataset(
        None,
        evidence_mode="evaluation_pit",
        canonical_contracts=_canonical_contracts_four(),
    )
    assert not dataset.empty
    assert "market_structure" in manifest["included_feature_families"]
    assert manifest["canonical_market_evidence"] is False
    assert manifest["market_evaluation_evidence"] is True
    assert manifest["research_promotion_eligible"] is False
    assert manifest["market_input"] == "canonical_contracts"


def test_evaluation_dataset_does_not_weaken_canonical_rights_gate() -> None:
    from commodity.market_data import DataContractViolation
    from commodity.research_dataset import build_pit_dataset

    with pytest.raises(DataContractViolation, match="rights"):
        build_pit_dataset(
            None,
            evidence_mode="canonical",
            canonical_contracts=_canonical_contracts_four(),
        )
