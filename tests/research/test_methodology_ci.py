import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "checks" / "check_research_methodology.py"


def test_methodology_ci_script_has_all_four_gates() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for gate in ("experiment-schema", "experiment-freeze-integrity", "experiment-verification", "programme-inference-integrity"):
        assert gate in text


def test_methodology_schema_gate_passes_repository_authority() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "experiment-schema"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_runs_all_methodology_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for gate in ("experiment-schema", "experiment-freeze-integrity", "experiment-verification", "programme-inference-integrity"):
        assert gate in workflow
