from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_change_docs_are_local_work_only() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert ".work/" in gitignore
    assert ".work/changes/<issue>-<slug>/" in agents
    assert "docs/development/<slice>/` is legacy historical evidence only" in agents
    assert ".work/changes/" in docs_map


def test_maintained_docs_do_not_link_retired_specific_docs() -> None:
    maintained = [ROOT / "README.md", ROOT / "docs" / "roadmap.md"]
    retired = ("kronos-indicator-fusion.md", "lenovo-laptop-specification-v0.1.md")

    for path in maintained:
        text = path.read_text(encoding="utf-8")
        for name in retired:
            assert name not in text

    assert not (ROOT / "docs" / "architecture" / retired[0]).exists()
    assert not (ROOT / "docs" / "environment" / retired[1]).exists()
