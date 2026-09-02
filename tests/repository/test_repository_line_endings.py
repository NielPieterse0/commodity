from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_repository_attributes_and_editor_policy_are_fail_closed() -> None:
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    editor = (ROOT / ".editorconfig").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in attrs
    assert "tests/fixtures/mdp3-golden/**/metadata.json -text" in attrs
    assert "*.bat text eol=crlf" in attrs and "*.cmd text eol=crlf" in attrs
    assert "end_of_line = lf" in editor
    assert "insert_final_newline = true" in editor
    assert "trim_trailing_whitespace = true" in editor
    assert "[*.{bat,cmd}]" in editor and "end_of_line = crlf" in editor


def test_repository_configuration_and_verification_wiring_are_pinned() -> None:
    configure = (ROOT / "scripts/environment/configure-repository.ps1").read_text(encoding="utf-8")
    verify = (ROOT / "scripts/verify.ps1").read_text(encoding="utf-8")
    for setting, value in (("core.autocrlf", "false"), ("core.eol", "lf"), ("core.safecrlf", "true")):
        assert f"git config --local {setting} {value}" in configure
        assert f"'{setting}' = '{value}'" in configure
    assert "configure-repository.ps1" in verify
    assert "git diff --check" in verify


def test_repository_owned_write_text_calls_declare_newline_policy() -> None:
    offenders: list[str] = []
    for base in (ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "write_text":
                    continue
                if not any(keyword.arg == "newline" for keyword in node.keywords):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert offenders == []


def test_git_attributes_resolve_lf_for_representative_text() -> None:
    proc = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", "research/programme/programme_evidence_map.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "text: auto" in proc.stdout
    assert "eol: lf" in proc.stdout


def test_configure_repository_applies_expected_git_settings_on_windows() -> None:
    if sys.platform != "win32":
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/environment/configure-repository.ps1")],
        cwd=ROOT,
        check=True,
    )
    expected = {"core.autocrlf": "false", "core.eol": "lf", "core.safecrlf": "true"}
    for key, value in expected.items():
        proc = subprocess.run(
            ["git", "config", "--local", "--get", key],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert proc.stdout.strip().lower() == value
