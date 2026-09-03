from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "rule_verification.json"


def load_registry() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1 or not data.get("rules"):
        raise ValueError("rule verification registry must be schema v1 with rules")
    ids = [rule["id"] for rule in data["rules"]]
    if len(ids) != len(set(ids)):
        raise ValueError("rule verification ids must be unique")
    for rule in data["rules"]:
        if rule.get("enforcement") != "pre-ci+ci" or not rule.get("verifier"):
            raise ValueError(f"local rule must declare pre-ci+ci verifier: {rule.get('id')}")
        if not (ROOT / rule["source"]).exists():
            raise ValueError(f"rule authority source does not exist: {rule['source']}")
    external_ids = [rule["id"] for rule in data.get("non_local_rules", [])]
    if len(external_ids) != len(set(external_ids)) or set(ids) & set(external_ids):
        raise ValueError("local and non-local rule ids must be unique")
    if any(not rule.get("reason") for rule in data.get("non_local_rules", [])):
        raise ValueError("non-local rules must declare why repository-local verification is impossible")
    return data


def command_for(parts: list[str]) -> list[str]:
    if parts[0].endswith(".py") or parts[0] in {"-m", "-c"}:
        return [sys.executable, *parts]
    return parts


def _powershell_commands(text: str) -> list[str]:
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("&") or re.match(r"^[A-Za-z][A-Za-z0-9_.-]*\s", stripped):
            commands.append(stripped)
    return commands


def _workflow_commands(text: str) -> list[str]:
    commands: list[str] = []
    run_block_indent: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if run_block_indent is not None:
            if stripped and indent <= run_block_indent:
                run_block_indent = None
            elif stripped and not stripped.startswith("#"):
                commands.append(stripped)
                continue
        run_line = stripped.removeprefix("- ")
        if not run_line.startswith("run:"):
            continue
        payload = run_line.removeprefix("run:").strip()
        if payload in {"|", ">", "|-", ">-"}:
            run_block_indent = indent
        elif payload and not payload.startswith("#"):
            commands.append(payload)
    return commands


def _normalized_command_tokens(command: str) -> list[str]:
    tokens = command.strip().split()
    if tokens and tokens[0] == "&":
        tokens = tokens[1:]
    if not tokens:
        return []
    interpreter = tokens[0].strip("'\"")
    normalized = interpreter.replace("\\", "/").lower()
    if (
        interpreter == "$RepositoryPython"
        or normalized.endswith(("/.venv/bin/python", "/.venv/scripts/python.exe"))
        or normalized in {".venv/bin/python", ".venv/scripts/python.exe"}
    ):
        tokens = tokens[1:]
    return [token.strip("'\"") for token in tokens]


def check_enforcement_wiring(data: dict) -> None:
    surfaces = {
        "pre-CI": _powershell_commands(
            (ROOT / data["pre_ci_entrypoint"]).read_text(encoding="utf-8-sig")
        ),
        "CI": _workflow_commands((ROOT / data["ci_workflow"]).read_text(encoding="utf-8-sig")),
    }
    for rule in data["rules"]:
        expected = list(rule["verifier"])
        command = " ".join(expected)
        for surface, commands in surfaces.items():
            if not any(_normalized_command_tokens(executable) == expected for executable in commands):
                raise ValueError(f"{rule['id']} is not wired into {surface}: {command}")



def run_doc_generator(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/docs/generate_docs.py", *args],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"documentation generator failed ({result.returncode})")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    try:
        data = load_registry()
        check_enforcement_wiring(data)
        if args.generate:
            run_doc_generator()
        if args.check_generated or args.run:
            run_doc_generator("--check")
        if args.run:
            for rule in data["rules"]:
                result = subprocess.run(command_for(rule["verifier"]), cwd=ROOT, check=False)
                if result.returncode:
                    raise ValueError(f"rule verifier failed: {rule['id']} ({result.returncode})")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"rule-verification: FAILED: {exc}")
        return 2
    print("rule-verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
