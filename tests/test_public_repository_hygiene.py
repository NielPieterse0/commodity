from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_repository_metadata_is_explicit() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (ROOT / "SECURITY.md").is_file()
    assert (ROOT / "CONTRIBUTING.md").is_file()
    assert "no project-wide open-source license has been granted yet" in readme
    assert "Live trading is disabled by policy" in readme


def test_ci_runs_public_hygiene_on_full_pr_history() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci
    assert "python scripts/check_public_hygiene.py" in ci


def test_generated_and_secret_state_is_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (
        ".env",
        ".work/",
        ".venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "artifacts/runs/*",
        "data/raw/*",
    ):
        assert entry in ignore


def test_public_hygiene_script_passes_current_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_public_hygiene.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_closing_keyword_guard_is_present() -> None:
    script = (ROOT / "scripts" / "check_public_hygiene.py").read_text(encoding="utf-8")
    assert "pull-request body contains a GitHub issue-closing keyword" in script
    assert "pull-request commit history contains a GitHub issue-closing keyword" in script


def test_closing_keyword_guard_covers_github_reference_forms() -> None:
    closing = runpy.run_path(str(ROOT / "scripts" / "check_public_hygiene.py"))["CLOSING"]
    for text in (
        "Fixes #123",
        "closes NielPieterse0/commodity#123",
        "Resolved https://github.com/NielPieterse0/commodity/issues/123",
    ):
        assert closing.search(text)
    assert not closing.search("Fix parser behavior; related to #123")
