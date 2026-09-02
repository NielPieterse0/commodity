from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "rule_verification.json"


def test_registry_maps_every_local_rule_to_verifier() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    assert data["schema_version"] == 1
    assert data["rules"]
    assert len({rule["id"] for rule in data["rules"]}) == len(data["rules"])
    for rule in data["rules"]:
        assert rule["source"]
        assert rule["verifier"]
        assert rule["enforcement"] == "pre-ci+ci"


def test_generated_rule_document_is_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/checks/check_rule_verification.py", "--check-generated"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pre_ci_and_ci_use_registry_gate() -> None:
    pre_ci = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8-sig")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8-sig")
    command = "scripts/checks/check_rule_verification.py --check-generated"
    assert command in pre_ci
    assert command in ci


def test_registry_gate_checks_every_verifier_is_wired_pre_ci_and_ci() -> None:
    script = (ROOT / "scripts" / "checks" / "check_rule_verification.py").read_text(encoding="utf-8")
    assert "check_enforcement_wiring(data)" in script
    assert "is not wired into" in script


def test_registry_gate_rejects_verifier_text_that_only_appears_in_comments(tmp_path: Path) -> None:
    checker = runpy.run_path(str(ROOT / "scripts" / "checks" / "check_rule_verification.py"))
    checker["check_enforcement_wiring"].__globals__["ROOT"] = tmp_path
    (tmp_path / "pre.ps1").write_text("# scripts/checks/example.py --check\n", encoding="utf-8")
    (tmp_path / "ci.yml").write_text("# scripts/checks/example.py --check\n", encoding="utf-8")
    data = {
        "pre_ci_entrypoint": "pre.ps1",
        "ci_workflow": "ci.yml",
        "rules": [{"id": "example", "verifier": ["scripts/checks/example.py", "--check"]}],
    }
    with pytest.raises(ValueError, match="not wired"):
        checker["check_enforcement_wiring"](data)


def test_canonical_verifier_checks_staged_and_unstaged_whitespace() -> None:
    script = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
    assert "git diff --cached --check" in script
    assert "git diff --check" in script


def test_non_local_binding_rules_are_explicitly_classified() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    ids = {rule["id"] for rule in data["non_local_rules"]}
    assert {
        "kis-runtime-governance",
        "work-management-state",
        "exact-head-merge-policy",
        "secret-history-review",
    } <= ids
    assert all(rule["reason"] for rule in data["non_local_rules"])
