from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
RAW_PYTHON = re.compile(
    r"(?<![A-Za-z0-9_./-])python(?:3(?:\.\d+)?)?(?:\.exe)?(?=\s)",
    re.IGNORECASE,
)
BOOTSTRAP = "python -m venv .venv"
LOCAL_CI = ".venv/bin/python"
LOCAL_WINDOWS = ".venv\\Scripts\\python.exe"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _workflow_failures(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    display_path = _display_path(path)
    failures: list[str] = []
    if "actions/setup-python" in text and BOOTSTRAP not in text:
        failures.append(f"{display_path}: missing checkout-local .venv bootstrap")
    run_block_indent: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        command: str | None = None
        if run_block_indent is not None:
            if stripped and indent <= run_block_indent:
                run_block_indent = None
            else:
                command = stripped
        run_line = stripped.removeprefix("- ")
        if run_line.startswith("run:"):
            payload = run_line.removeprefix("run:").strip()
            if payload in {"|", ">", "|-", ">-"}:
                run_block_indent = indent
                continue
            command = payload
        if command is None or not command or BOOTSTRAP in command:
            continue
        if RAW_PYTHON.search(command) and LOCAL_CI not in command:
            failures.append(
                f"{display_path}:{number}: repository Python bypasses checkout .venv"
            )
    return failures


def _enabled_kronos_runtime_failures() -> list[str]:
    models = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8-sig"))
    enabled = [
        name
        for name, cfg in models.get("models", {}).items()
        if cfg.get("enabled") is True and str(cfg.get("local_path", "")).replace("\\", "/") == "vendor/Kronos"
    ]
    if not enabled:
        return []
    lock = (ROOT / "requirements.kronos-cpu.lock.txt").read_text(encoding="utf-8")
    match = re.search(r"^# python: ([0-9]+\.[0-9]+)$", lock, re.MULTILINE)
    if not match:
        return ["requirements.kronos-cpu.lock.txt: missing governed Python version"]
    expected = match.group(1)
    observed = f"{sys.version_info.major}.{sys.version_info.minor}"
    if observed != expected:
        return [
            f"config/models.json: enabled Kronos runtime requires Python {expected}, active .venv is {observed}"
        ]
    return []


def check() -> list[str]:
    failures = [failure for path in WORKFLOWS for failure in _workflow_failures(path)]
    failures.extend(_enabled_kronos_runtime_failures())
    verify = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
    if LOCAL_WINDOWS not in verify:
        failures.append("scripts/verify.ps1: canonical verification does not bind repo-local .venv")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "CI may use its repository-pinned runner interpreter only to bootstrap" not in agents:
        failures.append("AGENTS.md: CI bootstrap exception is not explicit")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("python-environment: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("python-environment: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
