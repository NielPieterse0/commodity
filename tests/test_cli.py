import json
from pathlib import Path

import pytest

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


def test_research_metrics_parser_uses_governed_default_ledger() -> None:
    args = build_parser().parse_args(["check-research-metrics"])
    assert isinstance(args.ledger, Path)
    assert args.ledger.as_posix().endswith("artifacts/research-metrics/longitudinal-ledger.json")


def test_research_metrics_check_fails_closed_when_latest_stage_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_ledger", lambda _path: {"ledger": "stub"})
    monkeypatch.setattr(cli, "latest_closeout", lambda _ledger: {"status": "blocked", "blockers": ["x"]})
    args = build_parser().parse_args(["check-research-metrics", "--ledger", "ignored.json"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code == 2


def test_research_metrics_summary_writes_generated_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_ledger", lambda _path: {"ledger": "stub"})
    monkeypatch.setattr(cli, "render_markdown_summary", lambda _ledger: "# Generated\n")
    output = tmp_path / "summary.md"
    args = build_parser().parse_args([
        "summarize-research-metrics", "--ledger", "ignored.json", "--output", str(output)
    ])
    args.func(args)
    assert output.read_text(encoding="utf-8") == "# Generated\n"


def test_research_metrics_check_invalid_ledger_fails_closed(tmp_path, capsys) -> None:
    ledger = tmp_path / "invalid-ledger.json"
    ledger.write_text("{}", encoding="utf-8")
    args = build_parser().parse_args(["check-research-metrics", "--ledger", str(ledger)])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked"
    assert output["blockers"][0].startswith("invalid_ledger:")


def test_experiment_verify_power_parser() -> None:
    args = build_parser().parse_args([
        "experiment", "verify-power", "--prereg", "research/experiments/x/prereg.json"
    ])
    assert args.prereg == Path("research/experiments/x/prereg.json")


def test_experiment_freeze_parser_requires_binding_inputs() -> None:
    args = build_parser().parse_args([
        "experiment", "freeze", "exp-x", "--prereg", "research/experiments/x/prereg.json",
        "--tag", "experiment/exp-x/v1", "--output", "research/experiments/x/freeze.json",
    ])
    assert args.experiment_id == "exp-x"
    assert args.tag == "experiment/exp-x/v1"
    assert args.output == Path("research/experiments/x/freeze.json")


def test_experiment_verify_results_and_summary_parsers() -> None:
    verify_args = build_parser().parse_args([
        "experiment", "verify-results", "--prereg", "p.json", "--results", "r.json"
    ])
    assert verify_args.results == Path("r.json")
    summary_args = build_parser().parse_args([
        "experiment", "executive-summary", "--prereg", "p.json", "--results", "r.json",
        "--interpretation", "interpretation.md", "--output", "executive-summary.md",
    ])
    assert summary_args.output == Path("executive-summary.md")


def test_experiment_audit_leakage_and_reproduce_parsers() -> None:
    audit_args = build_parser().parse_args([
        "experiment", "audit-leakage", "--checks", "checks.json"
    ])
    assert audit_args.checks == Path("checks.json")
    reproduce_args = build_parser().parse_args([
        "experiment", "reproduce", "--reference", "reference.json", "--candidate", "candidate.json",
        "--tolerance", "tolerance.json",
    ])
    assert reproduce_args.byte is False
