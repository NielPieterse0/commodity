import json
from pathlib import Path

import pytest

from commodity import cli
from commodity.cli import build_parser


def test_capture_weather_run_parser_preserves_model_run() -> None:
    args = build_parser().parse_args([
        "capture-weather-run", "--run", "2024-08-13T00:00", "--latitude", "41.8781", "--longitude", "-87.6298", "--snapshot-id", "wx"
    ])
    assert args.model == "ecmwf_ifs"
    assert args.forecast_days == 10



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
        "experiment", "verify-power", "--prereg", "research/programmes/001-test/lines/001-line/experiments/001-x/prereg.json"
    ])
    assert args.prereg == Path("research/programmes/001-test/lines/001-line/experiments/001-x/prereg.json")


def test_experiment_freeze_parser_requires_binding_inputs() -> None:
    args = build_parser().parse_args([
        "experiment", "freeze", "001-x", "--prereg", "research/programmes/001-test/lines/001-line/experiments/001-x/prereg.json",
        "--dataset-manifest", "artifacts/x/dataset-manifest.json",
        "--tag", "experiment/001-x/v1", "--output", "research/programmes/001-test/lines/001-line/experiments/001-x/freeze.json",
    ])
    assert args.experiment_id == "001-x"
    assert args.tag == "experiment/001-x/v1"
    assert args.dataset_manifest == Path("artifacts/x/dataset-manifest.json")
    assert args.output == Path("research/programmes/001-test/lines/001-line/experiments/001-x/freeze.json")


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
