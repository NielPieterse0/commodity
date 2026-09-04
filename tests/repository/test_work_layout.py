from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "checks" / "check_work_layout.py"


def test_work_layout_does_not_require_ignored_runtime_worktrees_directory(tmp_path, monkeypatch):
    module = runpy.run_path(str(CHECK))
    work = tmp_path / ".work"
    (work / "changes").mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "change-workflow.ps1").write_text(
        "C:\\Projects\\kis-mcp change-governance.py git-workflow.py --repository $RepositoryRoot",
        encoding="utf-8",
    )
    monkeypatch.setitem(module["main"].__globals__, "ROOT", tmp_path)
    monkeypatch.setitem(module["main"].__globals__, "WORK", work)
    monkeypatch.setitem(module["main"].__globals__, "HISTORICAL", work / "historical")
    assert module["main"]() == 0
