from __future__ import annotations

import json
import runpy
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = runpy.run_path(str(ROOT / "scripts/checks/check_python_environment.py"))
workflow_failures = CHECKER["_workflow_failures"]


def _check(tmp_path: Path, text: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(text, encoding="utf-8")
    return workflow_failures(path)


def test_python_word_in_workflow_metadata_is_not_treated_as_execution(tmp_path: Path) -> None:
    failures = _check(
        tmp_path,
        "name: Python checks\nsteps:\n  - name: Python environment boundary\n",
    )
    assert failures == []


def test_raw_python_run_is_rejected_but_bootstrap_and_venv_runs_are_allowed(tmp_path: Path) -> None:
    bad = _check(tmp_path, "steps:\n  - run: python script.py\n")
    assert any("bypasses checkout .venv" in item for item in bad)

    good = _check(
        tmp_path,
        "steps:\n"
        "  - uses: actions/setup-python@v5\n"
        "  - run: python -m venv .venv\n"
        "  - run: .venv/bin/python script.py\n",
    )
    assert good == []


def test_multiline_run_block_is_scanned_for_raw_python(tmp_path: Path) -> None:
    failures = _check(
        tmp_path,
        "steps:\n"
        "  - run: |\n"
        "      echo start\n"
        "      python script.py\n",
    )
    assert any("bypasses checkout .venv" in item for item in failures)


def test_versioned_python_executables_are_rejected(tmp_path: Path) -> None:
    for executable in ("python3.11", "python3.12"):
        failures = _check(tmp_path, f"steps:\n  - run: {executable} script.py\n")
        assert any("bypasses checkout .venv" in item for item in failures), executable


def test_enabled_kronos_model_requires_pinned_runtime_python(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "models.json").write_text(
        json.dumps({"models": {"kronos_mini": {"enabled": True, "local_path": "vendor/Kronos"}}}),
        encoding="utf-8",
    )
    (tmp_path / "requirements.kronos-cpu.lock.txt").write_text(
        "# python: 3.11\n# platform: windows_x86_64\n# torch: 2.7.1\n",
        encoding="utf-8",
    )
    check_runtime = CHECKER["_enabled_kronos_runtime_failures"]
    check_runtime.__globals__["ROOT"] = tmp_path
    check_runtime.__globals__["sys"] = types.SimpleNamespace(
        version_info=types.SimpleNamespace(major=3, minor=13)
    )
    failures = check_runtime()
    assert any("requires Python 3.11" in item for item in failures)
