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

    for phrase in (
        "Big-picture research hierarchy",
        "L0 — Repository mandate",
        "L5 — Interpretation / diagnostic / exploration",
        "Governed research workflow",
        "This is the one authoritative end-to-end research workflow.",
        "Evidence from L4/L5 never silently becomes an L0/L1 claim",
        "| 1 | **L0 → L1** | Helicopter view |",
        "| 11 | **L4** | Verify |",
        "| 12 | **L5** | Compare observed versus expected |",
        "| 13 | **L5** | External post-result triangulation |",
        "| 14 | **L5 → L1/L2** | Programme conclusion |",
        "| 15 | **L1/L2** | Active revisit triggers |",
        "Step 1: Helicopter view",
        "Step 2: Gap",
        "Step 3: Evidence-led zoom-in",
        "Step 4: Quality literature",
        "Step 5: Mechanism",
        "Step 6: Hypothesis",
        "Step 7: Expected and disconfirming observations",
        "Step 8: Feasibility",
        "Step 9: Governed implementation + preregister and freeze if applicable",
        "Step 10: Execute",
        "Step 11: Verify",
        "Step 12: Compare observed versus expected",
        "Step 13: External post-result triangulation",
        "Step 14: Programme conclusion",
        "Step 15: Active revisit triggers",
        "information gained per genuinely independent confirmation evidence",
        "Development — available for fitting",
        "Rolling research OOS",
        "partly research-trained",
        "Reserved confirmation",
        "True forward evidence",
        "Reserved confirmation planning default: 20% of the usable chronological sample",
        ".work begins here",
        "Implementation quality gate",
        "independent oracle, reconstruction path, reference calculation or verifier",
        "replicating the relevant published/reference result",
        "correctly normalized, semantically verified data",
        "What preregistration must freeze",
        "market-implied comparator",
        "unbiased forecast",
        "independence is about non-use",
        "not secrecy",
        "preregistration_remote_bound: verified",
        "Scientific artifact and projection model",
        "record.json",
        "Reference direction is one-way",
        "Environment identity and reproduction semantics",
        "Logical reproduction",
        "Byte reproduction",
        "Bitwise equality is not universal scientific proof",
        "E0 — no useful evidence",
        "E6 — programme-level evidence",
        "Domain-specific leakage controls",
        "No known PIT violations detected by the declared checks",
        "Symmetric coherence/anomaly trigger classes",
        "Mandatory operator executive summary",
        "Where this fits",
        "Where the idea came from",
        "What we tested",
        "What we saw",
        "What it means for the bigger picture",
        "What next",
        "full affected regression suite",
        "Completion condition",
        "Exploratory research",
        "Confirmatory research",
        "What is immutable",
        "Human and machine",
    ):
        assert phrase in methodology
    assert "\n## Lifecycle\n" not in methodology
    assert "\n## Programme flow\n" not in methodology
    for phrase in (
        "`Commodity` is an experimental commodity-market research platform.",
        "## Primary objective",
        "1. screen tradable instruments and market states",
        "7. determine whether the integrated system remains robust",
    ):
        assert phrase in big_picture
    assert "## Repository" not in big_picture
    assert "L5" not in big_picture
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
