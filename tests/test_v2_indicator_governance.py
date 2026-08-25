from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import commodity.v2_indicator_contract as indicator_contract
from commodity.v2_indicator_contract import (
    CANDIDATE_ID,
    IMPLEMENTATION_SOURCE_PATHS,
    SPEC_PATH,
    SPEC_REVISION,
    EmpiricalReleaseBlocked,
    IndicatorContractError,
    bind_activation_contract,
    build_implementation_source_manifest,
    build_lineage_handoff,
    canonical_sha256,
    read_frozen_multiplicity_manifest,
    require_empirical_release,
)
from commodity.v2_indicator_weather_storage import (
    _build_weather_revision_from_verified_rows,
)
from commodity.v2_indicators import build_power_increments, build_weather_revision

ROOT = Path(__file__).resolve().parents[1]
BOUND_IMPLEMENTATION = "1" * 40
RUNTIME_REVISION = "2" * 40


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def _manifest() -> dict:
    return build_implementation_source_manifest(ROOT)


def _prospective_candidates() -> dict:
    candidates = _load("config/experiment_candidates.json")
    manifest = _manifest()
    candidate = candidates["candidates"][CANDIDATE_ID]
    candidate["preparation_revision"] = {
        "pr": 117,
        "head": SPEC_REVISION,
        "path": SPEC_PATH,
    }
    candidate["implementation_revision"] = {
        "pr": 99,
        "head": BOUND_IMPLEMENTATION,
        "path": "src/commodity/v2_indicator_contract.py",
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_manifest_paths": list(IMPLEMENTATION_SOURCE_PATHS),
    }
    return candidates


def _binding() -> dict:
    candidates = _prospective_candidates()
    return bind_activation_contract(
        _load("docs/development/v2-activation-preregistration/activation-contract.json"),
        candidates,
        read_frozen_multiplicity_manifest(ROOT),
    )


def _released(binding: dict, *, candidate_released: bool) -> dict:
    released = json.loads(json.dumps(binding))
    released["activation_execution_authorized"] = True
    gate = released["empirical_release_gate"]
    gate["88"]["satisfied"] = True
    gate["88"]["current_state"] = gate["88"]["required_state"]
    gate["release_state"]["83"] = candidate_released
    released.pop("binding_sha256")
    released["binding_sha256"] = canonical_sha256(released)
    return released


def test_committed_successor_173_freeze_stays_frozen_after_source_authority_change() -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _load("config/experiment_candidates.json")
    candidate = candidates["candidates"][CANDIDATE_ID]
    implementation = candidate["implementation_revision"]
    manifest = _manifest()

    assert candidate["preparation_revision"] == {
        "pr": 117,
        "head": SPEC_REVISION,
        "path": SPEC_PATH,
    }
    assert implementation["pr"] == 172
    assert implementation["head"] == "cc5decb5fb9d718edbbf706cf9169e3e73c15f0f"
    assert tuple(manifest["files"]) == IMPLEMENTATION_SOURCE_PATHS
    assert tuple(implementation["source_manifest_paths"]) == IMPLEMENTATION_SOURCE_PATHS
    assert implementation["source_manifest_sha256"] != manifest["manifest_sha256"]

    binding = bind_activation_contract(
        contract,
        candidates,
        read_frozen_multiplicity_manifest(ROOT),
    )
    with pytest.raises(EmpiricalReleaseBlocked, match="sources differ"):
        require_empirical_release(binding)


def test_pre_refreeze_pr98_preparation_head_is_rejected() -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _load("config/experiment_candidates.json")
    candidates["candidates"][CANDIDATE_ID]["preparation_revision"] = {
        "pr": 98,
        "head": "3e55213b967b590187223e2b286063c81672274a",
        "path": SPEC_PATH,
    }
    with pytest.raises(IndicatorContractError, match="preparation revision"):
        bind_activation_contract(
            contract,
            candidates,
            read_frozen_multiplicity_manifest(ROOT),
        )


def test_release_cannot_be_forged_by_rehashing_caller_binding() -> None:
    binding = _binding()
    for candidate_released in (False, True):
        forged = _released(binding, candidate_released=candidate_released)
        with pytest.raises(
            IndicatorContractError,
            match="differs from exact committed frozen authorities",
        ):
            require_empirical_release(forged)


def test_release_accepts_only_exact_reconstructed_committed_authority(monkeypatch) -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _prospective_candidates()
    multiplicity = read_frozen_multiplicity_manifest(ROOT)
    contract["execution_authorized"] = True
    candidates["candidates"][CANDIDATE_ID]["execution_authorized"] = True
    gate = contract["empirical_release_gate"]
    gate["88"]["satisfied"] = True
    gate["88"]["current_state"] = gate["88"]["required_state"]
    gate["release_state"]["83"] = True
    expected = bind_activation_contract(contract, candidates, multiplicity)

    state = {
        "contract": contract,
        "candidates": candidates,
        "multiplicity": multiplicity,
    }

    def _committed_json(_root: Path, relative: str, *, label: str) -> dict:
        del label
        if relative == indicator_contract.ACTIVATION_CONTRACT_PATH:
            return json.loads(json.dumps(state["contract"]))
        if relative == indicator_contract.EXPERIMENT_CANDIDATES_PATH:
            return json.loads(json.dumps(state["candidates"]))
        raise AssertionError(f"unexpected committed authority path: {relative}")

    monkeypatch.setattr(indicator_contract, "_read_committed_json", _committed_json)
    monkeypatch.setattr(
        indicator_contract,
        "read_frozen_multiplicity_manifest",
        lambda _root: state["multiplicity"],
    )

    require_empirical_release(expected)

    blocked_candidates = json.loads(json.dumps(candidates))
    blocked_candidates["candidates"][CANDIDATE_ID]["execution_authorized"] = False
    blocked = bind_activation_contract(contract, blocked_candidates, multiplicity)
    state["candidates"] = blocked_candidates
    with pytest.raises(EmpiricalReleaseBlocked, match="release the exact bound implementation"):
        require_empirical_release(blocked)
    state["candidates"] = candidates

    forged = json.loads(json.dumps(expected))
    forged["artifact_namespace"] = "artifacts/forged-83/"
    forged.pop("binding_sha256")
    forged["binding_sha256"] = canonical_sha256(forged)
    with pytest.raises(IndicatorContractError, match="committed frozen authorities"):
        require_empirical_release(forged)

    drifted_contract = json.loads(json.dumps(contract))
    drifted_contract["empirical_release_gate"]["release_state"]["83"] = False
    state["contract"] = drifted_contract
    with pytest.raises(IndicatorContractError, match="committed frozen authorities"):
        require_empirical_release(expected)

    state["contract"] = contract
    drifted_candidates = json.loads(json.dumps(candidates))
    drifted_candidates["candidates"][CANDIDATE_ID]["primary_variant"] = "I-FORGED"
    state["candidates"] = drifted_candidates
    with pytest.raises(EmpiricalReleaseBlocked, match="internally consistent"):
        require_empirical_release(expected)

    state["candidates"] = candidates
    state["multiplicity"] = b"{}\n"
    with pytest.raises(EmpiricalReleaseBlocked, match="internally consistent"):
        require_empirical_release(expected)


def test_release_guard_requires_all_three_authorization_inputs(monkeypatch) -> None:
    base_contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    base_candidates = _prospective_candidates()
    multiplicity = read_frozen_multiplicity_manifest(ROOT)
    state: dict[str, object] = {}

    def _committed_json(_root: Path, relative: str, *, label: str) -> dict:
        del label
        if relative == indicator_contract.ACTIVATION_CONTRACT_PATH:
            return json.loads(json.dumps(state["contract"]))
        if relative == indicator_contract.EXPERIMENT_CANDIDATES_PATH:
            return json.loads(json.dumps(state["candidates"]))
        raise AssertionError(f"unexpected committed authority path: {relative}")

    monkeypatch.setattr(indicator_contract, "_read_committed_json", _committed_json)
    monkeypatch.setattr(
        indicator_contract,
        "read_frozen_multiplicity_manifest",
        lambda _root: multiplicity,
    )

    for global_authorized in (False, True):
        for candidate_authorized in (False, True):
            for release_authorized in (False, True):
                contract = json.loads(json.dumps(base_contract))
                candidates = json.loads(json.dumps(base_candidates))
                contract["execution_authorized"] = global_authorized
                contract["empirical_release_gate"]["88"]["satisfied"] = True
                contract["empirical_release_gate"]["88"]["current_state"] = (
                    contract["empirical_release_gate"]["88"]["required_state"]
                )
                contract["empirical_release_gate"]["release_state"]["83"] = (
                    release_authorized
                )
                candidates["candidates"][CANDIDATE_ID]["execution_authorized"] = (
                    candidate_authorized
                )
                binding = bind_activation_contract(contract, candidates, multiplicity)
                state["contract"] = contract
                state["candidates"] = candidates

                if global_authorized and candidate_authorized and release_authorized:
                    require_empirical_release(binding)
                else:
                    with pytest.raises(
                        EmpiricalReleaseBlocked,
                        match="release the exact bound implementation",
                    ):
                        require_empirical_release(binding)


def test_release_reads_exact_committed_git_authorities_not_dirty_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _prospective_candidates()
    multiplicity = read_frozen_multiplicity_manifest(ROOT)
    contract["execution_authorized"] = True
    candidates["candidates"][CANDIDATE_ID]["execution_authorized"] = True
    gate = contract["empirical_release_gate"]
    gate["88"]["satisfied"] = True
    gate["88"]["current_state"] = gate["88"]["required_state"]
    gate["release_state"]["83"] = True
    expected = bind_activation_contract(contract, candidates, multiplicity)

    repo = tmp_path / "authority-repo"
    activation_path = repo / indicator_contract.ACTIVATION_CONTRACT_PATH
    candidates_path = repo / indicator_contract.EXPERIMENT_CANDIDATES_PATH
    multiplicity_path = repo / indicator_contract.MULTIPLICITY_MANIFEST_PATH
    module_path = repo / "src/commodity/v2_indicator_contract.py"
    for path in (activation_path, candidates_path, multiplicity_path, module_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    activation_path.write_text(
        json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    candidates_path.write_text(
        json.dumps(candidates, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    multiplicity_path.write_bytes(multiplicity)
    module_path.write_text("# authority-root marker\n", encoding="utf-8")

    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Commodity Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "freeze authorities"],
        check=True,
        capture_output=True,
    )

    dirty_contract = json.loads(json.dumps(contract))
    dirty_contract["execution_authorized"] = False
    dirty_contract["empirical_release_gate"]["88"]["satisfied"] = False
    dirty_contract["empirical_release_gate"]["release_state"]["83"] = False
    activation_path.write_text(
        json.dumps(dirty_contract, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    candidates_path.write_text("{}\n", encoding="utf-8")
    multiplicity_path.write_bytes(b"{}\n")

    monkeypatch.setattr(indicator_contract, "__file__", str(module_path))
    bound_manifest = candidates["candidates"][CANDIDATE_ID]["implementation_revision"][
        "source_manifest_sha256"
    ]
    monkeypatch.setattr(
        indicator_contract,
        "build_implementation_source_manifest",
        lambda _root: {"manifest_sha256": bound_manifest},
    )
    require_empirical_release(expected)

    committed_contract = indicator_contract._read_committed_json(
        repo,
        indicator_contract.ACTIVATION_CONTRACT_PATH,
        label="#81 activation contract",
    )
    assert committed_contract["execution_authorized"] is True
    assert activation_path.read_text(encoding="utf-8").find('"execution_authorized": false') >= 0


def test_activation_binding_rejects_multiplicity_drift() -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _prospective_candidates()
    manifest = _manifest()
    candidates["candidates"][CANDIDATE_ID]["implementation_revision"] = {
        "pr": 99,
        "head": BOUND_IMPLEMENTATION,
        "path": "src/commodity/v2_indicator_contract.py",
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_manifest_paths": list(IMPLEMENTATION_SOURCE_PATHS),
    }
    contract["frozen_execution_rules"]["multiple_testing_rule"]["families"] = [
        "F82_83_COMPONENT_PROMOTION",
        "F84_ALL_REQUIRED_COMPARATORS",
        "F85_SENSITIVITY",
    ]
    with pytest.raises(IndicatorContractError, match="multiplicity"):
        bind_activation_contract(
            contract,
            candidates,
            read_frozen_multiplicity_manifest(ROOT),
        )


def test_activation_binding_rejects_multiplicity_manifest_byte_drift() -> None:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    candidates = _prospective_candidates()
    exact = read_frozen_multiplicity_manifest(ROOT)
    with pytest.raises(IndicatorContractError, match="multiplicity manifest"):
        bind_activation_contract(contract, candidates, b"{}\n")
    with pytest.raises(IndicatorContractError, match="multiplicity manifest"):
        bind_activation_contract(contract, candidates, exact.replace(b"\n", b"\r\n"))


def test_source_manifest_is_exact_and_runtime_revision_is_separate() -> None:
    binding = _binding()
    manifest = _manifest()
    assert tuple(manifest["files"]) == IMPLEMENTATION_SOURCE_PATHS
    for relative in IMPLEMENTATION_SOURCE_PATHS:
        normalized = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n").replace(
            b"\r", b"\n"
        )
        assert manifest["files"][relative] == hashlib.sha256(normalized).hexdigest()
    handoff = build_lineage_handoff(
        binding=binding,
        input_frame=pd.DataFrame({"x": [1.0]}),
        feature_frame=pd.DataFrame({"y": [2.0]}),
        implementation_config={"fit_scope": "fold_train_only"},
        implementation_revision=RUNTIME_REVISION,
        runtime_source_manifest=manifest,
    )
    assert handoff["bound_implementation_revision"] == BOUND_IMPLEMENTATION
    assert handoff["runtime_code_revision"] == RUNTIME_REVISION
    assert handoff["implementation_source_manifest_sha256"] == manifest["manifest_sha256"]

    mutated = json.loads(json.dumps(manifest))
    first = IMPLEMENTATION_SOURCE_PATHS[0]
    mutated["files"][first] = "f" * 64
    body = {key: value for key, value in mutated.items() if key != "manifest_sha256"}
    mutated["manifest_sha256"] = canonical_sha256(body)
    with pytest.raises(IndicatorContractError, match="sources differ"):
        build_lineage_handoff(
            binding=binding,
            input_frame=pd.DataFrame({"x": [1.0]}),
            feature_frame=pd.DataFrame({"y": [2.0]}),
            implementation_config={"fit_scope": "fold_train_only"},
            implementation_revision=RUNTIME_REVISION,
            runtime_source_manifest=mutated,
        )


def _first_party_module_path(module: str) -> str | None:
    if module != "commodity" and not module.startswith("commodity."):
        return None
    parts = module.split(".")
    module_file = ROOT / "src" / Path(*parts).with_suffix(".py")
    package_file = ROOT / "src" / Path(*parts) / "__init__.py"
    for candidate in (module_file, package_file):
        if candidate.is_file():
            return candidate.relative_to(ROOT).as_posix()
    raise AssertionError(f"unresolved first-party import module: {module}")


def _first_party_imports(relative: str) -> set[str]:
    source = ROOT / relative
    tree = ast.parse(source.read_text(encoding="utf-8"))
    current_parts = source.relative_to(ROOT / "src").with_suffix("").parts
    current_package = current_parts[:-1]
    discovered: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(current_package) - (node.level - 1)
                if keep < 1:
                    raise AssertionError(f"invalid relative import in {relative}")
                base = list(current_package[:keep])
                if node.module:
                    base.extend(node.module.split("."))
                modules.append(".".join(base))
                if not node.module:
                    modules.extend(".".join([*base, alias.name]) for alias in node.names)
            elif node.module:
                modules.append(node.module)
                if node.module == "commodity":
                    modules.extend(f"commodity.{alias.name}" for alias in node.names)
        for module in modules:
            try:
                dependency = _first_party_module_path(module)
            except AssertionError:
                if module == "commodity" or module.startswith("commodity."):
                    raise
                continue
            if dependency is not None:
                discovered.add(dependency)
    return discovered


def test_source_manifest_closes_over_first_party_python_imports() -> None:
    manifest_paths = set(IMPLEMENTATION_SOURCE_PATHS)
    discovered: set[str] = set()
    for relative in IMPLEMENTATION_SOURCE_PATHS:
        if relative.startswith("src/commodity/") and relative.endswith(".py"):
            discovered.update(_first_party_imports(relative))

    assert "src/commodity/availability.py" in discovered
    assert "src/commodity/evidence_authority.py" in discovered
    assert discovered <= manifest_paths


def test_implementation_source_hash_is_newline_invariant(tmp_path: Path) -> None:
    digests = set()
    for name, raw in (
        ("lf.py", b"alpha\nbeta\n"),
        ("crlf.py", b"alpha\r\nbeta\r\n"),
        ("cr.py", b"alpha\rbeta\r"),
    ):
        path = tmp_path / name
        path.write_bytes(raw)
        digests.add(indicator_contract._sha256_file(path))
    assert len(digests) == 1

    changed = tmp_path / "changed.py"
    changed.write_bytes(b"alpha\ngamma\n")
    assert indicator_contract._sha256_file(changed) not in digests


def _source_policy() -> object:
    from commodity.v2_indicator_contract import parse_pinned_source_policy

    raw = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{SPEC_REVISION}:config/data_sources.json"]
    )
    return parse_pinned_source_policy(raw)


def _weather_rows() -> tuple[pd.DataFrame, pd.Timestamp]:
    policy = _source_policy()
    cfg = policy.payload["sources"]["weather"]
    anchors = [str(item["id"]) for item in cfg["v1_anchors"]]
    lead_start, lead_end = [int(value) for value in cfg["v1_feature_lead_hours"]]
    base = float(cfg["v1_degree_day_base_c"])
    cycle = int(cfg["v1_run_cycle_utc_hour"])
    current = pd.Timestamp("2026-01-02T00:00Z") + pd.Timedelta(hours=cycle)
    prior = current - pd.Timedelta(days=1)
    valid = pd.date_range(
        current + pd.Timedelta(hours=lead_start),
        current + pd.Timedelta(hours=lead_end),
        freq="h",
        inclusive="left",
    )
    source_id = cfg["accepted_source_ids"][0]
    rows = []
    for run_id, issued_at in (("prior", prior), ("current", current)):
        for anchor in anchors:
            for valid_at in valid:
                rows.append(
                    {
                        "run_id": run_id,
                        "issued_at": issued_at,
                        "available_at": issued_at + pd.Timedelta(hours=1),
                        "anchor_id": anchor,
                        "forecast_valid_at": valid_at,
                        "temperature_2m": base - 8.0,
                        "revision_status": "issued_run_immutable",
                        "source_id": source_id,
                    }
                )
    return pd.DataFrame(rows), current + pd.Timedelta(hours=2)


@pytest.mark.parametrize("column", ["available_at", "issued_at", "forecast_valid_at"])
def test_weather_pit_timestamps_require_explicit_timezone(column: str) -> None:
    rows, cutoff = _weather_rows()
    rows[column] = rows[column].dt.tz_localize(None)
    with pytest.raises(IndicatorContractError, match="timezone-aware"):
        _build_weather_revision_from_verified_rows(rows, cutoff, _source_policy())


def _power_rows() -> pd.DataFrame:
    policy = _source_policy()
    source_id = policy.payload["sources"]["nyiso_load_forecast"]["accepted_source_ids"][0]
    return pd.DataFrame(
        {
            "issued_at": pd.to_datetime(["2026-01-01T17:00Z", "2026-01-02T17:00Z"]),
            "available_at": pd.to_datetime(["2026-01-01T17:05Z", "2026-01-02T17:05Z"]),
            "forecast_valid_at": pd.to_datetime(["2026-01-02T05:00Z", "2026-01-03T05:00Z"]),
            "power_next_day_load_mean_mw": [100.0, 110.0],
            "power_next_day_load_max_mw": [120.0, 135.0],
            "power_next_day_load_min_mw": [90.0, 95.0],
            "revision_status": ["issued_run_immutable", "issued_run_immutable"],
            "source_id": [source_id, source_id],
        }
    )


@pytest.mark.parametrize("column", ["available_at", "issued_at", "forecast_valid_at"])
def test_power_pit_timestamps_require_explicit_timezone(column: str) -> None:
    rows = _power_rows()
    rows[column] = rows[column].dt.tz_localize(None)
    with pytest.raises(IndicatorContractError, match="timezone-aware"):
        build_power_increments(rows, "2026-01-02T18:00Z", _source_policy())


def test_weather_rejects_caller_rows_even_if_labelled_immutable() -> None:
    rows, cutoff = _weather_rows()

    with pytest.raises(IndicatorContractError, match="not release-authoritative"):
        build_weather_revision(rows, cutoff, _source_policy())
