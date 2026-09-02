from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_change_docs_are_local_work_only() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert ".work/" in gitignore
    assert ".work/changes/<issue>-<slug>/" in agents
    assert ".work/historical/docs/development/" in agents
    assert ".work/changes/" in docs_map
    assert not (ROOT / "docs" / "development").exists()
    assert ".work/historical/" in docs_map
    assert not (ROOT / "docs" / "references").exists()


def test_maintained_docs_explain_method_and_big_picture() -> None:
    methodology = (ROOT / "docs" / "research-methodology.md").read_text(encoding="utf-8")
    big_picture = (ROOT / "docs" / "big-picture.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for phrase in ("Exploratory research", "Confirmatory research", "What is immutable", "Human and machine"):
        assert phrase in methodology
    for phrase in ("Where the work came from", "What we have learned so far", "How we zoom in"):
        assert phrase in big_picture
    assert "data-engineering" in agents
    assert "MUST load" in agents

def test_maintained_docs_do_not_link_retired_specific_docs() -> None:
    maintained = [
        ROOT / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "roadmap.md",
        ROOT / "docs" / "big-picture.md",
        ROOT / "docs" / "research-methodology.md",
    ]
    retired = ("kronos-indicator-fusion.md", "lenovo-laptop-specification-v0.1.md")

    for path in maintained:
        text = path.read_text(encoding="utf-8")
        for name in retired:
            assert name not in text

    assert not (ROOT / "docs" / "architecture" / retired[0]).exists()
    assert not (ROOT / "docs" / "environment" / retired[1]).exists()
