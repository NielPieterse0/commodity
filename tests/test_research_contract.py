import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "experiment.schema.json"


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


def test_agents_md_requires_canonical_kis_skill_loading() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    expected_ids = {
        "bayesian-modeler", "commodity-market-data", "data-engineer",
        "dataset-auditor", "experiment-designer", "experiment-tracker",
        "develop-code", "develop-docs", "feature-engineer", "forecast-backtesting",
        "hyperparameter-optimizer", "model-evaluator", "model-trainer", "neural-network-engineer",
        "reproducibility-auditor", "statistical-analyst", "time-series-research",
    }
    assert "C:\\Projects\\.agents\\skills" in agents
    assert "runtime.search_skills" in agents
    assert "runtime.load_skill" in agents
    assert "runtime.read_skill_file" in agents
    assert all(name in agents for name in expected_ids)


def test_repo_contains_no_local_agent_skill_catalogue() -> None:
    local_roots = (".agents", ".openai", ".claude", ".cursor", ".codex")
    assert not [root for root in local_roots if (ROOT / root / "skills").exists()]


def test_repo_has_no_direct_local_skill_file_references() -> None:
    forbidden = (
        ".agents" + "/skills",
        ".openai" + "/skills",
        ".claude" + "/skills",
        "superpowers" + ":",
        "C:\\Projects\\kis-mcp\\.agents\\skills",
    )
    suffixes = {".md", ".py", ".toml", ".yml", ".yaml", ".json", ".txt"}
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] in {".git", ".work", "vendor"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(term in text for term in forbidden):
            violations.append(str(relative))
    assert not violations, f"direct/local skill references remain: {violations}"


def test_data_source_owner_selects_massive_without_unlocking_canonical_evidence() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    assert data["schema_version"] == 3
    canonical = data["sources"]["market_canonical"]
    assert canonical["provider"] == "massive_futures"
    assert canonical["approved_for_contract_price_history"] is True
    assert canonical["provides_contract_id"] is True
    assert canonical["provides_expiration"] is True
    assert canonical["provides_settlement"] is True
    assert canonical["historical_open_interest"] is False
    assert canonical["historical_volume"] is True
    assert canonical["account_history_validated"] is True
    assert canonical["history_earliest_verified_trade_date"] == "2024-08-13"
    assert canonical["non_display_backtesting_rights_verified"] is False
    assert canonical["backtest_evidence_allowed"] is False
    assert canonical["preservation_status"] == "resumable_snapshot_capture_ready"
    assert data["providers"]["massive_futures"]["env_key"] == "MASSIVE_API_KEY"
    assert data["providers"]["massive_futures"]["access"] == "authorization_bearer"
    prompt = data["sources"]["eia_nymex_prompt_history"]
    assert prompt["canonical_market_source"] is False
    assert prompt["coverage_end"] == "2024-04-05"
    for source_name in ("eia_storage", "eia_fundamentals", "eia_power", "cftc_cot", "weather"):
        source = data["sources"][source_name]
        assert source["point_in_time_required"] is True
        assert source["availability_reconstruction_status"] != "complete"
    power = data["sources"]["nyiso_load_forecast"]
    assert power["provider"] == "nyiso_mis"
    assert power["product"] == "ISO Load Forecast (P-7)"
    positioning = data["sources"]["cftc_cot"]
    assert positioning["contract_market_code"] == "023651"
    assert positioning["source_variant"] == "disaggregated_futures_only"
    assert positioning["availability_policy"]["research_pit_allowed"] is True
    assert power["availability_policy"]["research_pit_allowed"] is True
    assert power["availability_policy"]["revision_status"] == "issued_run_immutable"
    assert power["v1_archive_validation"].startswith("730_of_730")


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
    data = load_json(ROOT / "config" / "data_sources.json")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert assumptions["semantics"]["execution_authority"] is False
    assert assumptions["semantics"]["policy_owner"] == "config/policy.json"
    assert "Hard Constraints" not in agents
    assert policy["execution"]["live_trading_allowed"] is False
    assert assumptions["assumptions"]["canonical_market_provider"]["excluded_for_now"] == []
    assert data["sources"]["market_canonical"]["provider"] == "massive_futures"
    assert data["sources"]["databento_henry_hub_probe"]["canonical_market_source"] is False


def test_raw_contracts_are_canonical_and_roll_is_derived_policy() -> None:
    data = load_json(ROOT / "config" / "data_sources.json")
    assumptions = load_json(ROOT / "config" / "assumptions.json")
    continuous = data["canonical_contract_schema"]["continuous_contract"]
    policy = assumptions["assumptions"]["continuous_series_policy"]
    assert continuous["authoritative_storage"] == "raw_per_contract"
    assert continuous["adjustment_method"] == "none_stored_raw"
    assert continuous["cross_contract_returns_allowed"] is False
    assert continuous["default_roll_policy"] == "volume_crossover_dte_v1"
    assert policy["default_roll_policy"] == "volume_crossover_dte_v1"
    assert policy["policy"]["confirmation_sessions"] == 2
    assert policy["policy"]["forced_roll_days_before_expiry"] == 3
    assert continuous["roll_policy_owner"].startswith("config/assumptions.json")


def test_volatility_direction_is_additive_experiment_candidate() -> None:
    current = load_json(ROOT / "config" / "experiment.json")
    candidates = load_json(ROOT / "config" / "experiment_candidates.json")
    candidate = candidates["candidates"]["ng-volatility-direction-v1"]
    assert current["experiment_id"] == "ng-next-session-return-baseline-v1"
    assert candidate["does_not_replace"].startswith("config/experiment.json")
    assert candidate["targets"][0]["metric"] == "qlike"


def test_active_experiment_uses_pit_core_tournament_contract() -> None:
    experiment = load_json(ROOT / "config" / "experiment.json")
    models = load_json(ROOT / "config" / "models.json")["models"]
    dataset = experiment["dataset"]
    tournament = experiment["tournament"]
    assert dataset["evidence_mode"] == "research_pit"
    assert dataset["leakage_enforcement"] == "pit_dataset_contract"
    assert dataset["promotion_completeness"] == "full_v1"
    assert tournament["split_strategy"] == "expanding_walk_forward"
    assert tournament["models"] == ["naive", "ridge", "hist_gb"]
    assert models["hist_gb"]["baseline_implementation"] == "hist_gradient_boosting_return"


def test_agents_md_requires_kis_change_flow() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "runtime.load_skill" in agents
    assert "runtime.search_skills" in agents
    assert "runtime.read_skill_file" in agents
    assert "`.work/` linked worktree" in agents
    assert "PR-completion workflow" in agents
    assert "KIS owns repository-change effect classification" in agents
    assert "currently advertised KIS change workflow" in agents
    assert "default-branch change remains subject to KIS exact-change verification" in agents


def test_phase_b_evidence_classifies_all_required_exogenous_families() -> None:
    evidence = load_json(
        ROOT
        / "docs"
        / "development"
        / "v1-research-completion"
        / "phase-b-evidence.json"
    )
    assert evidence["schema_version"] == 1
    assert evidence["phase"] == "B"
    assert evidence["full_v1_ready"] is False
    assert tuple(evidence["families"]) == (
        "storage",
        "weather",
        "power",
        "positioning",
    )
    for family, result in evidence["families"].items():
        assert result["family"] == family
        assert result["verdict"] in {"fit", "fit-with-caveats", "not-fit"}
        assert result["blockers"] or result["full_v1_ready"]


def test_phase_c_evidence_fails_closed_when_phase_b_is_not_ready() -> None:
    evidence = load_json(
        ROOT
        / "docs"
        / "development"
        / "v1-research-completion"
        / "phase-c-evidence.json"
    )
    assert evidence["schema_version"] == 1
    assert evidence["phase"] == "C"
    assert evidence["phase_b_full_v1_ready"] is False
    assert evidence["full_v1_freeze_status"] == "blocked"
    assert evidence["empirical_dataset_audit"]["status"] == "not_run_blocked"
    assert evidence["decision"]["phase_d_allowed"] is False
    assert evidence["machinery"]["synthetic_fixtures_are_research_evidence"] is False
