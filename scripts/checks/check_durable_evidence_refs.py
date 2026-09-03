from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
JSON_ROOTS = (
    ROOT / "config",
    ROOT / "research",
    ROOT / "artifacts" / "research-metrics",
)
CURRENT_PREFIXES = (
    "config/",
    "contracts/",
    "research/",
    "artifacts/",
    "docs/",
    "scripts/",
    "src/",
    "tests/",
    ".github/",
    "data/acquisition-recipes/",
)
CURRENT_ROOT_FILES = {"AGENTS.md", "README.md", "SECURITY.md", "CONTRIBUTING.md"}
SKIP_PATH_KEYS = {"forbidden_maintained_paths"}


def _git_history_has(path: str) -> bool:
    result = subprocess.run(
        ["git", "log", "--all", "-n", "1", "--format=%H", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _inside_legacy_experiment(path: Path) -> bool:
    return any((parent / "legacy-record.json").is_file() for parent in path.parents)


def _iter_json() -> list[Path]:
    return sorted(
        path
        for root in JSON_ROOTS
        if root.is_dir()
        for path in root.rglob("*.json")
        if not _inside_legacy_experiment(path)
    )


def _walk(value: Any, *, key: str | None = None):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk(child, key=str(child_key))
        return
    if isinstance(value, list):
        for child in value:
            yield from _walk(child, key=key)
        return
    if not isinstance(value, str) or key in SKIP_PATH_KEYS:
        return
    normalized = value.replace("\\", "/")
    if normalized.startswith("git-history:"):
        yield "history", normalized.removeprefix("git-history:").split("#", 1)[0]
        return
    if normalized.startswith(("http://", "https://", "ftp://")):
        return
    reference = normalized.split("#", 1)[0]
    if key == "source_refs" and "/" in reference:
        yield "current_file", reference
    elif reference.startswith(CURRENT_PREFIXES) or reference in CURRENT_ROOT_FILES:
        yield "current", reference


def check() -> list[str]:
    failures: list[str] = []
    for path in _iter_json():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for mode, reference in _walk(payload):
            if not reference or any(token in reference for token in ("*", "{", "}", "<", ">")):
                continue
            target = ROOT / reference
            if mode == "current_file" and not target.is_file():
                failures.append(f"{path.relative_to(ROOT)}: missing current evidence {reference}")
            elif mode == "current" and not target.exists():
                failures.append(f"{path.relative_to(ROOT)}: missing current repository reference {reference}")
            elif mode == "history" and not _git_history_has(reference):
                failures.append(f"{path.relative_to(ROOT)}: unresolved git-history evidence {reference}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("durable-evidence-refs: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("durable-evidence-refs: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
