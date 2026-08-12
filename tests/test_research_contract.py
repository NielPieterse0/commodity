import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "experiment.schema.json"
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


def test_research_period_far_future_end_is_explicitly_a_sentinel() -> None:
    experiment = load_json(ROOT / "config" / "experiment.json")
    period = experiment["research_period"]
    assert period["end"] == "2100-01-01"
    assert period["end_semantics"] == "open_ended_far_future_sentinel"


def test_forecast_experiment_does_not_own_strategy_or_cost_assumptions() -> None:
    experiment = load_json(ROOT / "config" / "experiment.json")
    signal = load_json(ROOT / "config" / "signal_policy.json")
    simulation = load_json(ROOT / "config" / "simulation.json")
    assert "cost_model" not in experiment
    assert signal["default_policy"] in signal["policies"]
    default_simulation = simulation["simulations"][simulation["default_simulation"]]
    assert simulation["semantics"]["research_backtesting_available"] is True
    assert simulation["semantics"]["execution_authority"] is False
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
        "develop-code", "develop-docs", "feature-engineer", "forecast-backtesting",
        "hyperparameter-optimizer", "model-evaluator", "model-trainer", "neural-network-engineer",
        "reproducibility-auditor", "statistical-analyst", "time-series-research",
    }
    assert expected == {path.parent.name for path in SKILL_ROOT.glob("*/SKILL.md")}
    assert all(name in agents for name in expected)
    for name in ("experiment-designer", "experiment-tracker"):
        skill = SKILL_ROOT / name / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        relative_contract = "../../../contracts/experiment.schema.json"
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


def test_data_source_owner_selects_massive_without_unlocking_canonical_evidence() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    assert data["schema_version"] == 2
    canonical = data["sources"]["market_canonical"]
    assert canonical["provider"] == "massive_futures"
    assert canonical["approved_for_contract_price_history"] is True
    assert canonical["provides_contract_id"] is True
    assert canonical["provides_expiration"] is True
    assert canonical["provides_settlement"] is True
    assert canonical["historical_open_interest"] is False
    assert canonical["backtest_evidence_allowed"] is False
    assert data["providers"]["massive_futures"]["env_key"] == "MASSIVE_API_KEY"
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


def test_legacy_skill_trees_are_removed() -> None:
    assert not (ROOT / "ml-research-core").exists()
    assert not (ROOT / "domain-skills").exists()
    assert SCHEMA.exists()


def test_work_area_is_local_only_and_non_authoritative() -> None:
    assert ".work/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Use `.work/` for local implementation scratch" in agents
    assert "MUST NOT depend on it" in agents


def test_saxo_probe_cannot_promote_itself_to_canonical_evidence() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    source = data["sources"]["saxo_henry_hub_probe"]
    assert data["providers"]["saxo_openapi_sim"]["read_only"] is True
    assert source["provider"] == "saxo_openapi_sim"
    assert source["provides_settlement"] is False
    assert source["canonical_market_source"] is False
    assert source["backtest_evidence_allowed"] is False


def test_revisable_constraints_live_in_assumption_registry() -> None:
    assumptions = load_json(ROOT / "config" / "assumptions.json")
    policy = load_json(ROOT / "config" / "policy.json")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert assumptions["semantics"]["execution_authority"] is False
    assert assumptions["semantics"]["policy_owner"] == "config/policy.json"
    assert "Hard Constraints" not in agents
    assert policy["execution"]["live_trading_allowed"] is False
    assert assumptions["assumptions"]["canonical_market_provider"]["excluded_for_now"] == ["databento"]


def test_raw_contracts_are_canonical_and_roll_is_derived_policy() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    continuous = data["canonical_contract_schema"]["continuous_contract"]
    assert continuous["authoritative_storage"] == "raw_per_contract"
    assert continuous["adjustment_method"] == "none_stored_raw"
    assert continuous["default_roll_policy"] is None
    assert continuous["cross_contract_returns_allowed"] is False
    assert continuous["roll_policy_owner"].startswith("config/assumptions.json")


def test_volatility_direction_is_additive_experiment_candidate() -> None:
    current = load_json(ROOT / "config" / "experiment.json")
    candidates = load_json(ROOT / "config" / "experiment_candidates.json")
    candidate = candidates["candidates"]["ng-volatility-direction-v1"]
    assert current["experiment_id"] == "ng-next-session-return-baseline-v1"
    assert candidate["does_not_replace"].startswith("config/experiment.json")
    assert candidate["targets"][0]["metric"] == "qlike"


def test_agents_md_requires_development_controller_and_worktree_pr_flow() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Every repository work run MUST load one primary development controller immediately after reading governing repository instructions" in agents
    assert ".agents/skills/develop-code/SKILL.md" in agents
    assert ".agents/skills/develop-docs/SKILL.md" in agents
    assert "`.work/` linked worktree" in agents
    assert "PR-completion workflow" in agents
