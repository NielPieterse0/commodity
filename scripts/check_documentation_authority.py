from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "documentation_authority.json"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise ValueError(message)


def load_manifest() -> dict:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        fail("documentation authority manifest schema_version must be 1")
    return value


def maintained_markdown() -> set[str]:
    paths = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("*.md")}
    docs = ROOT / "docs"
    for path in docs.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if not rel.startswith("docs/development/"):
            paths.add(rel)
    return paths


def check_declared_ownership(manifest: dict) -> list[str]:
    declared = manifest["maintained_documents"]
    paths = [item["path"] for item in declared]
    if len(paths) != len(set(paths)):
        fail("maintained document path declared more than once")
    owners: dict[str, str] = {}
    for item in declared:
        path = ROOT / item["path"]
        if not path.is_file():
            fail(f"declared maintained document missing: {item['path']}")
        for authority in item["owns"]:
            if authority in owners:
                fail(f"authority class has multiple owners: {authority}: {owners[authority]}, {item['path']}")
            owners[authority] = item["path"]
    actual = maintained_markdown()
    expected = set(paths)
    if actual != expected:
        fail(f"maintained document set drift: undeclared={sorted(actual-expected)} missing={sorted(expected-actual)}")
    return paths


def check_forbidden_paths(manifest: dict) -> None:
    for rel in manifest.get("forbidden_maintained_paths", []):
        if (ROOT / rel).exists():
            fail(f"forbidden maintained path exists: {rel}")


def check_links(paths: list[str]) -> None:
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for raw in LINK_RE.findall(text):
            target = raw.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = ((ROOT / rel).parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                fail(f"maintained doc link escapes repository: {rel} -> {raw}")
            if not resolved.exists():
                fail(f"broken maintained doc link: {rel} -> {raw}")


def normalized_paragraphs(paths: list[str]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for block in re.split(r"\n\s*\n", text):
            compact = " ".join(block.split())
            if len(compact) < 180 or compact.startswith(("|", "```", "#")):
                continue
            key = compact.casefold()
            seen.setdefault(key, []).append(rel)
    return seen


def check_copy_duplication(paths: list[str]) -> None:
    duplicates = {text: refs for text, refs in normalized_paragraphs(paths).items() if len(set(refs)) > 1}
    if duplicates:
        sample_refs = next(iter(duplicates.values()))
        fail(f"substantial maintained prose duplicated across documents: {sorted(set(sample_refs))}")


def changed_paths() -> list[str]:
    base = os.environ.get("GITHUB_BASE_SHA") or os.environ.get("GITHUB_EVENT_BEFORE")
    if not base:
        return []
    result = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "HEAD"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def check_legacy_freeze(manifest: dict) -> None:
    prefix = manifest["legacy_prefix"]
    touched = sorted(path for path in changed_paths() if path.startswith(prefix))
    if touched:
        fail(f"frozen legacy documentation changed: {touched}")


def main() -> int:
    try:
        manifest = load_manifest()
        paths = check_declared_ownership(manifest)
        check_forbidden_paths(manifest)
        check_links(paths)
        check_copy_duplication(paths)
        check_legacy_freeze(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"documentation-authority: FAILED: {exc}")
        return 2
    print("documentation-authority: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
