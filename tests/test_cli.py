from commodity.cli import build_parser


def test_capture_massive_v1_parser_owns_curve_horizon_and_pacing() -> None:
    args = build_parser().parse_args([
        "capture-massive-v1", "--end", "2026-08-12", "--snapshot-id", "massive-v1"
    ])
    assert args.start == "2024-08-13"
    assert args.curve_months == 12
    assert args.minimum_interval == 12.5


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
