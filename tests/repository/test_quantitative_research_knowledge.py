from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "config" / "quantitative_research_knowledge.json"
SCHEMA = ROOT / "contracts" / "quantitative_research_knowledge.schema.json"

CORE_SOURCE_IDS = {"ml4t3", "fpp3", "fde", "dmls"}
REQUIRED_DOMAINS = {
    "data_engineering",
    "forecasting",
    "financial_ml_research",
    "feature_engineering",
    "model_selection_and_tuning",
    "temporal_integrity_and_leakage",
    "backtesting_and_trading",
    "production_monitoring",
}
REQUIRED_PLAYBOOKS = {
    "temporal_integrity",
    "target_definition",
    "feature_engineering",
    "validation_and_cross_validation",
    "model_selection_and_tuning",
    "forecast_evaluation",
    "backtesting",
}


def load_router() -> dict:
    return json.loads(ROUTER.read_text(encoding="utf-8"))


def test_router_contract_and_required_authorities() -> None:
    data = load_router()
    assert data["schema_version"] == 1
    assert SCHEMA.is_file()
    assert CORE_SOURCE_IDS <= set(data["sources"])
    assert data["sources"]["ddia2"]["tier"] == 2
    assert REQUIRED_DOMAINS <= set(data["routing"])
    assert REQUIRED_PLAYBOOKS <= set(data["playbooks"])

    for source_id, source in data["sources"].items():
        assert source["url"].startswith("https://")
        assert source["access"]
        assert source["license_or_copyright"]
        assert source["authority_domains"], source_id


def test_routing_matches_phase_zero_authority_contract() -> None:
    routing = load_router()["routing"]
    assert routing["data_engineering"]["primary_sources"] == ["fde"]
    assert routing["forecasting"]["primary_sources"] == ["fpp3"]
    assert routing["financial_ml_research"]["primary_sources"] == ["ml4t3"]
    assert routing["feature_engineering"]["primary_sources"] == ["ml4t3"]
    assert "fpp3" in routing["feature_engineering"]["secondary_sources"]
    assert routing["model_selection_and_tuning"]["primary_sources"] == ["ml4t3"]
    assert "dmls" in routing["model_selection_and_tuning"]["secondary_sources"]
    assert routing["temporal_integrity_and_leakage"]["primary_sources"] == ["dmls"]
    assert "ml4t3" in routing["temporal_integrity_and_leakage"]["secondary_sources"]
    assert routing["backtesting_and_trading"]["primary_sources"] == ["ml4t3"]
    assert routing["production_monitoring"]["primary_sources"] == ["dmls"]


def test_playbooks_are_executable_and_cited() -> None:
    data = load_router()
    for playbook_id in REQUIRED_PLAYBOOKS:
        playbook = data["playbooks"][playbook_id]
        assert playbook["purpose"]
        assert len(playbook["rules"]) >= 4
        for index, rule in enumerate(playbook["rules"], start=1):
            assert rule["order"] == index
            assert rule["rule_id"].startswith(f"{playbook_id}-")
            assert rule["instruction"]
            assert set(rule["source_ids"]) <= set(data["sources"])
            assert rule["owner_refs"]


def test_methodology_map_distinguishes_coverage_from_gaps() -> None:
    data = load_router()
    coverage = {entry["status"] for entry in data["methodology_map"]}
    assert {"covered", "partial", "missing"} <= coverage
    assert data["missing_controls"]
    gap_ids = {item["control_id"] for item in data["missing_controls"]}
    assert "nested-walk-forward-model-selection" in gap_ids
    assert "training-serving-skew-and-drift" in gap_ids


def test_router_preserves_confirmation_and_copyright_boundaries() -> None:
    data = load_router()
    boundary = data["protected_confirmation_boundary"]
    assert boundary["outcomes_must_remain_unread"] is True
    assert boundary["outcomes_must_not_influence_design_or_selection"] is True
    assert data["copyright_policy"]["copy_book_prose"] is False
    assert data["copyright_policy"]["third_party_code_requires_license_review"] is True


def test_router_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/checks/check_quantitative_research_knowledge.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_router_is_projected_for_agents_and_humans() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "quantitative-research-knowledge.md").read_text(encoding="utf-8")

    assert "consult `config/quantitative_research_knowledge.json`" in agents
    assert "Quantitative Research Knowledge Router" in docs
    assert "## Executable playbooks" in docs
    assert "## Methodology coverage" in docs
    assert "## Deferred controls" in docs
    assert "Reserved-confirmation outcomes remain unread" in docs
