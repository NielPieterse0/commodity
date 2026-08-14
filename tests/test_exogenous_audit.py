import pandas as pd


def _research_frame(start: str, periods: int = 4, *, exact: bool = False) -> pd.DataFrame:
    issued = pd.date_range(start, periods=periods, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "issued_at": issued,
            "available_at": issued + pd.Timedelta(hours=6, minutes=10),
            "availability_status": "verified" if exact else "reconstructed_conservative",
            "revision_status": "issued_run_immutable",
            "source_id": "open_meteo_single_runs_v1",
            "source_raw_sha256": "a" * 64,
            "signal": range(periods),
        }
    )


def test_full_coverage_conservative_source_is_fit_with_caveats() -> None:
    from commodity.exogenous_audit import audit_exogenous_family

    result = audit_exogenous_family(
        family="weather",
        source_name="weather",
        frame=_research_frame("2025-01-01", periods=5),
        required_start="2025-01-01T06:10:00Z",
        required_end="2025-01-05T06:10:00Z",
    )
    assert result.verdict == "fit-with-caveats"
    assert result.full_v1_ready is True
    assert "conservative_availability" in result.caveats
    assert result.blockers == ()


def test_incomplete_coverage_is_not_fit_even_when_rows_are_pit_safe() -> None:
    from commodity.exogenous_audit import audit_exogenous_family

    result = audit_exogenous_family(
        family="weather",
        source_name="weather",
        frame=_research_frame("2025-01-03", periods=2),
        required_start="2025-01-01",
        required_end="2025-01-05",
    )
    assert result.verdict == "not-fit"
    assert result.full_v1_ready is False
    assert "coverage_incomplete" in result.blockers


def test_coverage_uses_when_evidence_was_available_not_observation_time() -> None:
    from commodity.exogenous_audit import audit_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-01-01", "2025-01-31"], utc=True),
            "available_at": pd.to_datetime(["2025-01-05", "2025-02-01"], utc=True),
            "availability_status": ["verified", "verified"],
            "revision_status": ["point_in_time", "point_in_time"],
            "signal": [1.0, 2.0],
        }
    )
    result = audit_exogenous_family(
        family="storage",
        source_name="archive_storage",
        frame=frame,
        required_start="2025-01-02",
        required_end="2025-01-31",
    )
    assert result.verdict == "not-fit"
    assert "coverage_incomplete" in result.blockers
    assert result.coverage_start == "2025-01-05T00:00:00+00:00"


def test_revised_current_snapshot_is_not_fit_for_research_pit() -> None:
    from commodity.exogenous_audit import audit_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": [pd.Timestamp("2025-01-03T00:00:00Z")],
            "available_at": [pd.Timestamp("2025-01-09T15:30:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["current_snapshot_revised_history"],
            "signal": [1.0],
        }
    )
    result = audit_exogenous_family(
        family="storage",
        source_name="eia_storage",
        frame=frame,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.verdict == "not-fit"
    assert "research_pit_ineligible_rows" in result.blockers


def test_missing_evidence_is_explicitly_not_fit() -> None:
    from commodity.exogenous_audit import audit_exogenous_family

    result = audit_exogenous_family(
        family="positioning",
        source_name="cftc_cot",
        frame=None,
        required_start="2025-01-01",
        required_end="2025-12-31",
    )
    assert result.verdict == "not-fit"
    assert result.blockers == ("preserved_pit_evidence_missing",)


def test_configured_storage_requires_wngsr_vintage_source_and_raw_lineage() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2024-12-20", "2025-01-03", "2025-01-10", "2025-01-17", "2025-01-24"],
                utc=True,
            ),
            "available_at": pd.to_datetime(
                [
                    "2024-12-27T15:30Z",
                    "2025-01-09T15:30Z",
                    "2025-01-16T15:30Z",
                    "2025-01-23T15:30Z",
                    "2025-01-30T15:30Z",
                ]
            ),
            "availability_status": ["reconstructed_conservative"] * 5,
            "revision_status": ["point_in_time"] * 5,
            "source_id": ["eia_wngsr_vintage_reconstruction"] * 5,
            "source_variant": ["original_plus_published_revisions"] * 5,
            "history_raw_sha256": ["a" * 64] * 5,
            "revisions_raw_sha256": ["b" * 64] * 5,
            "signal": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="storage",
        source_name="eia_storage",
        frame=frame,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.verdict == "fit-with-caveats"
    assert result.full_v1_ready is True
    assert "bounded_forward_fill" in result.caveats

    current_snapshot = frame.assign(source_id="eia_api_v2")
    result = audit_configured_exogenous_family(
        family="storage",
        source_name="eia_storage",
        frame=current_snapshot,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.full_v1_ready is False
    assert "configured_storage_source_identity_mismatch" in result.blockers


def test_configured_storage_rejects_internal_gap_beyond_max_staleness() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2024-12-20", "2025-01-24"], utc=True),
            "available_at": pd.to_datetime(
                ["2024-12-27T15:30Z", "2025-01-30T15:30Z"], utc=True
            ),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["point_in_time"] * 2,
            "source_id": ["eia_wngsr_vintage_reconstruction"] * 2,
            "source_variant": ["original_plus_published_revisions"] * 2,
            "history_raw_sha256": ["a" * 64] * 2,
            "revisions_raw_sha256": ["b" * 64] * 2,
            "signal": [1.0, 2.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="storage",
        source_name="eia_storage",
        frame=frame,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.verdict == "not-fit"
    assert result.full_v1_ready is False
    assert "max_staleness_exceeded" in result.blockers


def test_configured_power_uses_nyiso_issued_vintages_not_eia_revised_history() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    available = pd.date_range("2025-01-01T17:00Z", "2025-01-31T17:00Z", freq="D")
    frame = pd.DataFrame(
        {
            "observed_for": available.normalize(),
            "issued_at": available - pd.Timedelta(days=1),
            "available_at": available,
            "availability_status": ["reconstructed_conservative"] * len(available),
            "revision_status": ["issued_run_immutable"] * len(available),
            "signal": range(len(available)),
        }
    )
    result = audit_configured_exogenous_family(
        family="power",
        source_name="nyiso_load_forecast",
        frame=frame,
        required_start="2025-01-01T17:00Z",
        required_end="2025-01-31T17:00Z",
    )
    assert result.verdict == "fit-with-caveats"
    assert result.full_v1_ready is True
    assert result.blockers == ()

    try:
        audit_configured_exogenous_family(
            family="power",
            source_name="eia_power",
            frame=frame,
            required_start="2025-01-01",
            required_end="2025-01-31",
        )
    except ValueError as exc:
        assert "nyiso_load_forecast" in str(exc)
    else:
        raise AssertionError("EIA-930 revised history must not satisfy the configured V1 power source")


def test_configured_power_allows_25_hour_fall_dst_daily_spacing() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-11-01", "2025-11-02"], utc=True),
            "issued_at": pd.to_datetime(["2025-11-01T14:00Z", "2025-11-02T15:00Z"]),
            "available_at": pd.to_datetime(["2025-11-01T16:00Z", "2025-11-02T17:00Z"]),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["issued_run_immutable"] * 2,
            "signal": [1.0, 2.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="power",
        source_name="nyiso_load_forecast",
        evidence_source_id="nyiso_p7_iso_load_forecast",
        frame=frame,
        required_start="2025-11-01T16:00Z",
        required_end="2025-11-02T17:00Z",
    )
    assert result.full_v1_ready is True
    assert "max_staleness_exceeded" not in result.blockers


def test_configured_power_rejects_missing_daily_issues() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-01-01", "2025-01-04"], utc=True),
            "issued_at": pd.to_datetime(["2024-12-31T17:00Z", "2025-01-03T17:00Z"]),
            "available_at": pd.to_datetime(["2025-01-01T17:00Z", "2025-01-04T17:00Z"]),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["issued_run_immutable"] * 2,
            "signal": [1.0, 2.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="power",
        source_name="nyiso_load_forecast",
        evidence_source_id="nyiso_p7_iso_load_forecast",
        frame=frame,
        required_start="2025-01-01T17:00Z",
        required_end="2025-01-04T17:00Z",
    )
    assert result.full_v1_ready is False
    assert "max_staleness_exceeded" in result.blockers


def test_configured_positioning_requires_cftc_variant_and_raw_lineage() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(
                ["2024-12-24", "2025-01-07", "2025-01-21"], utc=True
            ),
            "available_at": pd.to_datetime(
                ["2025-01-01", "2025-01-14", "2025-01-28"], utc=True
            ),
            "availability_status": ["reconstructed_conservative"] * 3,
            "revision_status": ["point_in_time"] * 3,
            "source_id": ["cftc_disaggregated_futures_only_023651"] * 3,
            "source_variant": ["disaggregated_futures_only"] * 3,
            "source_raw_sha256": ["b" * 64] * 3,
            "signal": [1.0, 2.0, 3.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="positioning",
        source_name="cftc_cot",
        frame=frame,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.verdict == "fit-with-caveats"
    assert result.full_v1_ready is True
    assert "bounded_forward_fill" in result.caveats

    wrong_variant = frame.assign(source_variant="futures_and_options_combined")
    result = audit_configured_exogenous_family(
        family="positioning",
        source_name="cftc_cot",
        frame=wrong_variant,
        required_start="2025-01-01",
        required_end="2025-01-31",
    )
    assert result.full_v1_ready is False
    assert "positioning_source_variant_invalid" in result.blockers


def test_configured_positioning_allows_declared_publication_hiatus() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-09-23", "2025-09-30"], utc=True),
            "available_at": pd.to_datetime(
                ["2025-10-01T03:59Z", "2025-11-20T04:59Z"], utc=True
            ),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["point_in_time"] * 2,
            "source_id": ["cftc_disaggregated_futures_only_023651"] * 2,
            "source_variant": ["disaggregated_futures_only"] * 2,
            "source_raw_sha256": ["b" * 64] * 2,
            "signal": [1.0, 2.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="positioning",
        source_name="cftc_cot",
        frame=frame,
        required_start="2025-10-01T03:59Z",
        required_end="2025-11-20T04:59Z",
    )
    assert result.full_v1_ready is True
    assert "max_staleness_exceeded" not in result.blockers
    assert "source_declared_publication_hiatus" in result.caveats


def test_configured_positioning_rejects_unexplained_long_gap() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = pd.DataFrame(
        {
            "observed_for": pd.to_datetime(["2025-09-16", "2025-09-23"], utc=True),
            "available_at": pd.to_datetime(
                ["2025-10-01T03:59Z", "2025-11-20T04:59Z"], utc=True
            ),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["point_in_time"] * 2,
            "source_id": ["cftc_disaggregated_futures_only_023651"] * 2,
            "source_variant": ["disaggregated_futures_only"] * 2,
            "source_raw_sha256": ["b" * 64] * 2,
            "signal": [1.0, 2.0],
        }
    )
    result = audit_configured_exogenous_family(
        family="positioning",
        source_name="cftc_cot",
        frame=frame,
        required_start="2025-10-01T03:59Z",
        required_end="2025-11-20T04:59Z",
    )
    assert result.full_v1_ready is False
    assert "max_staleness_exceeded" in result.blockers


def test_required_family_audit_returns_all_four_families() -> None:
    from commodity.exogenous_audit import audit_required_exogenous_families

    results = audit_required_exogenous_families(
        frames={"weather": _research_frame("2025-01-01", periods=5)},
        required_start="2025-01-01T06:10:00Z",
        required_end="2025-01-05T06:10:00Z",
    )
    assert tuple(results) == ("storage", "weather", "power", "positioning")
    assert results["weather"].verdict == "fit-with-caveats"
    assert results["storage"].verdict == "not-fit"
    assert results["power"].verdict == "not-fit"
    assert results["positioning"].verdict == "not-fit"



def test_configured_weather_requires_v1_source_identity_and_raw_hash() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = _research_frame("2025-01-01", periods=3)
    result = audit_configured_exogenous_family(
        family="weather",
        source_name="weather",
        frame=frame,
        required_start="2025-01-01T06:10Z",
        required_end="2025-01-03T06:10Z",
    )
    assert result.full_v1_ready is True

    missing_hash = frame.drop(columns=["source_raw_sha256"])
    result = audit_configured_exogenous_family(
        family="weather",
        source_name="weather",
        frame=missing_hash,
        required_start="2025-01-01T06:10Z",
        required_end="2025-01-03T06:10Z",
    )
    assert result.full_v1_ready is False
    assert "weather_raw_lineage_missing" in result.blockers


def test_configured_weather_rejects_missing_daily_run() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    frame = _research_frame("2025-01-01", periods=4).drop(index=1).reset_index(drop=True)
    result = audit_configured_exogenous_family(
        family="weather",
        source_name="weather",
        frame=frame,
        required_start="2025-01-01T06:10Z",
        required_end="2025-01-04T06:10Z",
    )
    assert result.full_v1_ready is False
    assert "max_staleness_exceeded" in result.blockers


def test_configured_weather_allows_declared_issued_run_gaps() -> None:
    from commodity.exogenous_audit import audit_configured_exogenous_family

    issued = pd.to_datetime(
        ["2025-08-04T00:00Z", "2025-08-10T00:00Z"]
    )
    frame = pd.DataFrame(
        {
            "issued_at": issued,
            "available_at": issued + pd.Timedelta(hours=6, minutes=10),
            "availability_status": ["reconstructed_conservative"] * len(issued),
            "revision_status": ["issued_run_immutable"] * len(issued),
            "source_id": ["open_meteo_single_runs_v1"] * len(issued),
            "source_raw_sha256": ["a" * 64] * len(issued),
            "signal": range(len(issued)),
        }
    )
    result = audit_configured_exogenous_family(
        family="weather",
        source_name="weather",
        frame=frame,
        required_start="2025-08-04T06:10Z",
        required_end="2025-08-10T06:10Z",
    )
    assert result.full_v1_ready is True
    assert result.verdict == "fit-with-caveats"
    assert "max_staleness_exceeded" not in result.blockers
    assert "source_declared_issued_run_gap" in result.caveats
