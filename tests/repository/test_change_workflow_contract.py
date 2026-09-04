from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_repository_change_workflow_delegates_to_shared_kis_engine() -> None:
    script = (ROOT / "scripts" / "change-workflow.ps1").read_text(encoding="utf-8")
    assert "C:\\Projects\\kis-mcp" in script
    assert "change-governance.py" in script
    assert "git-workflow.py" in script
    assert "--repository $RepositoryRoot" in script
    assert not (ROOT / "scripts" / "change-governance.py").exists()
    assert not (ROOT / "scripts" / "git-workflow.py").exists()


def test_research_originated_spec_is_mapping_not_duplicate_authority() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template = (ROOT / ".work" / "changes" / "_template" / "spec.md").read_text(encoding="utf-8")
    methodology = (ROOT / "config" / "research_methodology.json").read_text(encoding="utf-8")
    assert "nested workflow" in agents
    assert "thin science-to-repository implementation mapping" in agents
    assert "Do not restate, reinterpret, or extend the scientific design" in template
    assert '"nested_research_kis_workflow"' in methodology
    assert "implementation_ready" in methodology
    assert "validity inputs" in methodology
