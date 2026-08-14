import json

from commodity import cli
from commodity.cli import build_parser


def test_capture_canonical_market_v1_parser_owns_curve_bound_not_provider_pacing() -> None:
    args = build_parser().parse_args([
        "capture-canonical-market-v1",
        "--end",
        "2026-08-12",
        "--snapshot-id",
        "canonical-v1",
    ])
    assert args.start == "2024-08-13"
    assert args.curve_contracts == 12
    assert not hasattr(args, "minimum_interval")


def test_capture_eia_v1_parser_is_bounded_by_dates() -> None:
    args = build_parser().parse_args([
        "capture-eia-v1", "--start", "2024-08-13", "--end", "2026-08-12", "--snapshot-id", "eia-v1"
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"


def test_capture_weather_run_parser_preserves_model_run() -> None:
    args = build_parser().parse_args([
        "capture-weather-run", "--run", "2024-08-13T00:00", "--latitude", "41.8781", "--longitude", "-87.6298", "--snapshot-id", "wx"
    ])
    assert args.model == "ecmwf_ifs"
    assert args.forecast_days == 10



def test_capture_weather_v1_window_parser_is_date_bounded() -> None:
    args = build_parser().parse_args([
        "capture-weather-v1-window",
        "--end",
        "2026-08-12",
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"
    assert not hasattr(args, "run")
    assert not hasattr(args, "latitude")



def test_capture_cftc_v1_window_parser_is_date_bounded() -> None:
    args = build_parser().parse_args([
        "capture-cftc-v1-window",
        "--end",
        "2026-08-12",
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"
    assert not hasattr(args, "year")



def test_capture_wngsr_v1_window_parser_is_date_bounded() -> None:
    args = build_parser().parse_args([
        "capture-wngsr-v1-window",
        "--end",
        "2026-08-12",
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"
    assert not hasattr(args, "week")


def test_capture_nyiso_v1_window_parser_is_date_bounded() -> None:
    args = build_parser().parse_args([
        "capture-nyiso-v1-window",
        "--end",
        "2026-08-12",
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"
    assert not hasattr(args, "month")


def test_audit_v1_exogenous_parser_is_local_and_date_bounded() -> None:
    args = build_parser().parse_args([
        "audit-v1-exogenous",
        "--end",
        "2026-08-12",
    ])
    assert args.start == "2024-08-13"
    assert args.end == "2026-08-12"
    assert args.output.endswith("phase-b-evidence.json")


def test_audit_v1_exogenous_reports_all_missing_families(tmp_path, monkeypatch) -> None:
    def missing_loader(*_args):
        raise ValueError("missing preserved snapshot")

    monkeypatch.setattr(cli, "load_wngsr_v1_window", missing_loader)
    monkeypatch.setattr(cli, "load_weather_v1_window", missing_loader)
    monkeypatch.setattr(cli, "load_nyiso_v1_window", missing_loader)
    monkeypatch.setattr(cli, "load_cftc_v1_window", missing_loader)

    output = tmp_path / "phase-b-evidence.json"
    args = build_parser().parse_args([
        "audit-v1-exogenous",
        "--start", "2024-08-13",
        "--end", "2026-08-12",
        "--snapshot-root", str(tmp_path / "snapshots"),
        "--output", str(output),
    ])
    args.func(args)

    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["full_v1_ready"] is False
    assert set(evidence["families"]) == {"storage", "weather", "power", "positioning"}
    for family in evidence["families"].values():
        assert "preserved_pit_evidence_missing" in family["blockers"]
        assert family["load_error"] == "missing preserved snapshot"
