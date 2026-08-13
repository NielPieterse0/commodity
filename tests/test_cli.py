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
