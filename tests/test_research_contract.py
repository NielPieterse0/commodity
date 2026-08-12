import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "ml-research-core" / "contracts" / "experiment.schema.json"
SKILL_ROOT = ROOT / ".agents" / "skills"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_experiment_schema_v2_closes_reconstruction_gaps() -> None:
    schema = load_json(SCHEMA)
    required = set(schema["required"])
    assert schema["properties"]["schema_version"]["const"] == 2
    assert {"experiment_id", "run_id", "forecast", "features", "lineage"} <= required
    assert schema["properties"]["results"]["properties"]["primary_metric_value"]["type"] == "number"
    assert schema["properties"]["decision"]["properties"]["scope"]["const"] == "research_only"
    code_revision = schema["properties"]["lineage"]["properties"]["code_revision"]
    assert code_revision["type"] == "object"
    assert {"commit_sha", "working_tree_dirty", "working_tree_diff_sha256"} == set(code_revision["required"])


def test_major_contract_sections_are_closed() -> None:
    schema = load_json(SCHEMA)
    for section in ("forecast", "split", "features", "model", "training", "evaluation", "controls", "results", "decision", "lineage"):
        assert schema["properties"][section]["additionalProperties"] is False


def test_forecast_experiment_does_not_own_strategy_or_cost_assumptions() -> None:
    experiment = load_json(ROOT / "config" / "experiment.json")
    signal = load_json(ROOT / "config" / "signal_policy.json")
    simulation = load_json(ROOT / "config" / "simulation.json")
    assert "cost_model" not in experiment
    assert signal["default_policy"] in signal["policies"]
    default_simulation = simulation["simulations"][simulation["default_simulation"]]
    assert default_simulation["canonical_evidence_allowed"] is False
    assert "cost_model" in default_simulation


def test_commodity_research_stages_do_not_authorize_live_execution() -> None:
    stages = load_json(ROOT / "config" / "research_stages.json")
    policy = load_json(ROOT / "config" / "policy.json")
    assert stages["semantics"]["live_trading_authority"] is False
    assert stages["semantics"]["execution_permission_owner"] == "config/policy.json"
    assert policy["execution"]["live_trading_allowed"] is False


def test_agents_md_declares_repo_skill_discovery() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert ".agents/skills/<skill-name>/SKILL.md" in agents
    expected = {
        "bayesian-modeler", "commodity-market-data", "data-engineer",
        "dataset-auditor", "experiment-designer", "experiment-tracker",
        "feature-engineer", "forecast-backtesting", "hyperparameter-optimizer",
        "model-evaluator", "model-trainer", "neural-network-engineer",
        "reproducibility-auditor", "statistical-analyst", "time-series-research",
    }
    assert expected == {path.parent.name for path in SKILL_ROOT.glob("*/SKILL.md")}
    assert all(name in agents for name in expected)
    for name in ("experiment-designer", "experiment-tracker"):
        skill = SKILL_ROOT / name / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        relative_contract = "../../../ml-research-core/contracts/experiment.schema.json"
        assert relative_contract in text
        assert (skill.parent / relative_contract).resolve() == SCHEMA.resolve()


def test_generic_core_has_no_commodity_specific_rules() -> None:
    domain = {"commodity-market-data", "time-series-research", "forecast-backtesting"}
    generic = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in SKILL_ROOT.glob("*/SKILL.md")
        if path.parent.name not in domain
    )
    forbidden = (
        "henry hub",
        "natural gas",
        "cftc",
        "storage report",
        "futures expiration",
        "contract roll",
    )
    assert not [term for term in forbidden if term in generic]


def test_data_source_owner_blocks_noncanonical_market_evidence() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    assert data["schema_version"] == 2
    assert data["sources"]["market_canonical"]["backtest_evidence_allowed"] is False
    prompt = data["sources"]["eia_nymex_prompt_history"]
    assert prompt["canonical_market_source"] is False
    assert prompt["coverage_end"] == "2024-04-05"
    for source_name in ("eia_storage", "cftc_cot", "weather"):
        source = data["sources"][source_name]
        assert source["point_in_time_required"] is True
        assert source["availability_reconstruction_status"] != "complete"


def test_provider_connection_settings_have_single_owner() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    providers = data["providers"]
    for source in data["sources"].values():
        provider_name = source.get("provider")
        if provider_name in providers:
            assert "api_base" not in source
            assert "env_key" not in source
