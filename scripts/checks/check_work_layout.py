from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".work"
HISTORICAL = WORK / "historical"


def _is_junction(path: Path) -> bool:
    checker = getattr(os.path, "isjunction", None)
    return bool(checker and checker(path))


def main() -> int:
    failures: list[str] = []
    if not WORK.exists():
        print("work-layout: passed (no local .work state)")
        return 0

    changes = WORK / "changes"
    worktrees = WORK / "worktrees"
    if not changes.is_dir():
        failures.append("missing .work/changes directory")
    elif changes.is_symlink() or _is_junction(changes):
        failures.append(".work/changes must be checkout-local, not a link/junction")
    if worktrees.exists() and not worktrees.is_dir():
        failures.append(".work/worktrees exists but is not a directory")
    elif worktrees.is_dir() and (worktrees.is_symlink() or _is_junction(worktrees)):
        failures.append(".work/worktrees must be checkout-local when present, not a link/junction")

    forbidden = [
        HISTORICAL / "changes",
        HISTORICAL / ".worktrees",
        ROOT / ".worktrees",
    ]
    for path in forbidden:
        if path.exists():
            failures.append(f"legacy governed-work container exists: {path.relative_to(ROOT)}")

    if HISTORICAL.is_dir():
        for marker in HISTORICAL.rglob(".git"):
            if marker.is_file():
                failures.append(
                    "Git worktree marker remains under historical: "
                    f"{marker.parent.relative_to(ROOT)}"
                )

    workflow = ROOT / "scripts" / "change-workflow.ps1"
    if not workflow.is_file():
        failures.append("missing scripts/change-workflow.ps1 KIS workflow entrypoint")
    else:
        text = workflow.read_text(encoding="utf-8")
        required = ("C:\\Projects\\kis-mcp", "change-governance.py", "git-workflow.py", "--repository $RepositoryRoot")
        missing = [item for item in required if item not in text]
        if missing:
            failures.append("change-workflow.ps1 does not delegate to the shared KIS engine: " + ", ".join(missing))
    for duplicate in (ROOT / "scripts" / "change-governance.py", ROOT / "scripts" / "git-workflow.py"):
        if duplicate.exists():
            failures.append(f"repository duplicates shared KIS governance engine: {duplicate.relative_to(ROOT)}")

    if failures:
        print("work-layout: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 2
    print("work-layout: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
