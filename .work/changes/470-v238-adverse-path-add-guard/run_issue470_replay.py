from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "scripts/research/run_issue465_block1_controller_v3.py"
EVIDENCE = Path(__file__).resolve().parent / "evidence" / "replay"


def load_runner():
    spec = importlib.util.spec_from_file_location("issue470_v3_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load controller-v3 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_outputs(runner) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    names = (
        "PREFLIGHT", "INVENTORY", "REENTRY", "CANDIDATES", "ORACLE",
        "ATTRIBUTE_ORACLE", "ORACLE_PREDICTOR", "PRIMITIVE_ORACLE_PREDICTOR",
        "TRIALS", "BRAIN", "EFFECTIVENESS_SURFACES", "CONSEQUENCES",
        "LEDGER", "RESULT",
    )
    for name in names:
        original = getattr(runner, name)
        setattr(runner, name, EVIDENCE / original.name)
    runner.CHECKPOINT_ROOT = EVIDENCE / "candidate-replays"
    runner.GENERATION_ROOT = EVIDENCE / "generations"
    runner.CURRENT_GENERATION = EVIDENCE / "current-generation.json"
    runner.SCORE_ARTIFACTS = (
        runner.PRIMITIVE_ORACLE_PREDICTOR,
        runner.ATTRIBUTE_ORACLE,
        runner.ORACLE_PREDICTOR,
        runner.ORACLE,
        runner.TRIALS,
        runner.BRAIN,
        runner.EFFECTIVENESS_SURFACES,
        runner.CONSEQUENCES,
        runner.LEDGER,
        runner.RESULT,
    )


def main() -> None:
    runner = load_runner()
    configure_outputs(runner)
    preflight = runner.preflight()
    if preflight.get("status") != "PASS":
        raise RuntimeError(f"#470 replay preflight failed: {preflight}")
    result = runner.score_block()
    output = EVIDENCE / "issue470-replay-return.json"
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result.get("status"),
        "total_net_return": result.get("performance", {}).get("total_net_return"),
        "future_invariance": result.get("implementation_evidence", {}).get(
            "full_future_invariance_mutation_replay_passed"
        ),
        "output": str(output),
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
