from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:#\d+|[\w.-]+/[\w.-]+#\d+|https://github\.com/[^\s]+/issues/\d+)",
    re.IGNORECASE,
)
LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:\\(?:Projects|Users)\\|C:/Projects/|/(?:home|Users)/[^/\s]+/)",
    re.IGNORECASE,
)
SENSITIVE_PARTS = {".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "quarantine"}
EXEMPT_LOCAL_PATHS = {
    Path("scripts/check_public_hygiene.py"),
    Path("tests/test_research_contract.py"),
}
EXEMPT_PREFIXES = (Path("docs/development"),)


def tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [Path(item.decode()) for item in out.split(b"\0") if item]


def check_tracked_state(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for rel in paths:
        if any(part.lower() in SENSITIVE_PARTS for part in rel.parts):
            findings.append(f"tracked generated/sensitive path: {rel}")
        if rel.suffix.lower() not in {".md", ".json", ".py", ".toml", ".yml", ".yaml", ".txt"}:
            continue
        if rel in EXEMPT_LOCAL_PATHS or any(rel.is_relative_to(prefix) for prefix in EXEMPT_PREFIXES):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        if LOCAL_PATH.search(text):
            findings.append(f"machine-local path in current repository text: {rel}")
    return findings


def check_pr_text() -> list[str]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return []
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull = event.get("pull_request")
    if not pull:
        return []
    findings: list[str] = []
    if CLOSING.search(pull.get("body") or ""):
        findings.append("pull-request body contains a GitHub issue-closing keyword")
    base = pull["base"]["sha"]
    head = pull["head"]["sha"]
    messages = subprocess.check_output(
        ["git", "log", "--format=%B%x00", f"{base}..{head}"], cwd=ROOT, text=True
    )
    if CLOSING.search(messages):
        findings.append("pull-request commit history contains a GitHub issue-closing keyword")
    return findings


def main() -> int:
    findings = check_tracked_state(tracked_files()) + check_pr_text()
    if findings:
        print("Public-repository hygiene check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Public-repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
