from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _require_clean_diff(*args: str) -> list[str]:
    result = _git("diff", "--check", *args)
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip()
    return [detail or f"git diff --check {' '.join(args)} failed"]


def _committed_range() -> tuple[str, ...] | None:
    event = os.getenv("EVENT_NAME", "")
    pr_base = os.getenv("PR_BASE_SHA", "")
    pr_head = os.getenv("PR_HEAD_SHA", "")
    if event == "pull_request" and pr_base and pr_head:
        return (pr_base, pr_head)
    before = os.getenv("BEFORE_SHA", "")
    head = os.getenv("GITHUB_SHA", "")
    if before and before != ZERO_SHA and head and _git("cat-file", "-e", f"{before}^{{commit}}").returncode == 0:
        return (before, head)
    if _git("rev-parse", "--verify", "origin/main").returncode == 0:
        merge_base = _git("merge-base", "origin/main", "HEAD")
        if merge_base.returncode == 0:
            base = merge_base.stdout.strip()
            head_sha = _git("rev-parse", "HEAD").stdout.strip()
            if base and head_sha and base != head_sha:
                return (base, head_sha)
    if _git("rev-parse", "--verify", "HEAD^").returncode == 0:
        return ("HEAD^", "HEAD")
    return None


def check() -> list[str]:
    failures = []
    failures.extend(_require_clean_diff("--cached"))
    failures.extend(_require_clean_diff())
    committed = _committed_range()
    if committed is not None:
        failures.extend(_require_clean_diff(*committed))
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("git-whitespace: FAILED")
        for failure in failures:
            print(failure)
        return 1
    print("git-whitespace: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
