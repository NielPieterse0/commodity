from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "documentation_authority.json"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise ValueError(message)


def load_manifest() -> dict:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if value.get("schema_version") != 2:
        fail("documentation authority manifest schema_version must be 2")
    return value


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
                fail(f"authority class has multiple owners: {authority}")
            owners[authority] = item["path"]
    return paths

def check_forbidden_paths(manifest: dict) -> None:
    for rel in manifest.get("forbidden_maintained_paths", []):
        if (ROOT / rel).exists():
            fail(f"forbidden maintained path exists: {rel}")


def check_generated_docs(manifest: dict) -> None:
    generated = manifest["generated_documentation"]
    generator = ROOT / generated["generator"]
    source = ROOT / generated["narrative_source"]
    if not generator.is_file() or not source.is_file():
        fail("generated documentation source or generator missing")
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail((result.stdout + result.stderr).strip())


def check_links(paths: list[Path]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for raw in LINK_RE.findall(text):
            target = raw.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                fail(f"document link escapes repository: {path.relative_to(ROOT)} -> {raw}")
            if not resolved.exists():
                fail(f"broken document link: {path.relative_to(ROOT)} -> {raw}")

def main() -> int:
    try:
        manifest = load_manifest()
        maintained = check_declared_ownership(manifest)
        check_forbidden_paths(manifest)
        check_generated_docs(manifest)
        link_paths = [ROOT / rel for rel in maintained]
        link_paths.extend((ROOT / "docs").rglob("*.md"))
        check_links(link_paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"documentation-authority: FAILED: {exc}")
        return 2
    print("documentation-authority: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
