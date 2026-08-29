from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any


class InferenceError(ValueError):
    """Raised when programme-level inference evidence is malformed."""


SUPPORTED_PROCEDURES = {
    "white_reality_check",
    "hansen_spa",
    "model_confidence_set",
    "benjamini_hochberg",
    "justified_alternative",
}


def _require_series(values: dict[str, list[float]], *, minimum: int = 3) -> tuple[list[str], int]:
    if not values:
        raise InferenceError("inference input cannot be empty")
    names = sorted(values)
    lengths = {len(values[name]) for name in names}
    if len(lengths) != 1:
        raise InferenceError("all inference series must have the same length")
    n = lengths.pop()
    if n < minimum:
        raise InferenceError(f"inference series require at least {minimum} observations")
    for name in names:
        if any(not math.isfinite(float(value)) for value in values[name]):
            raise InferenceError(f"non-finite inference value for {name}")
    return names, n


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _moving_block_indices(n: int, block_length: int, rng: random.Random) -> list[int]:
    if not 1 <= block_length <= n:
        raise InferenceError("block_length must be inside [1, n]")
    result: list[int] = []
    while len(result) < n:
        start = rng.randrange(n)
        result.extend((start + offset) % n for offset in range(block_length))
    return result[:n]


def _bootstrap_pvalue(observed: float, bootstrap: list[float]) -> float:
    return (1 + sum(value >= observed for value in bootstrap)) / (len(bootstrap) + 1)


def _inputs_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def benjamini_hochberg(pvalues: dict[str, float], *, alpha: float) -> dict[str, Any]:
    if not 0 < alpha < 1:
        raise InferenceError("alpha must be inside (0, 1)")
    if not pvalues:
        raise InferenceError("p-value family cannot be empty")
    ordered = sorted((float(value), name) for name, value in pvalues.items())
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value, _ in ordered):
        raise InferenceError("p-values must be finite and inside [0, 1]")
    threshold_index = 0
    count = len(ordered)
    for rank, (value, _) in enumerate(ordered, start=1):
        if value <= alpha * rank / count:
            threshold_index = rank
    rejected = sorted(name for _, name in ordered[:threshold_index])
    return {
        "procedure": "benjamini_hochberg",
        "alpha": alpha,
        "family_size": count,
        "rejected": rejected,
    }


def white_reality_check(
    loss_differentials: dict[str, list[float]],
    *,
    bootstrap_samples: int = 2000,
    block_length: int = 5,
    seed: int = 0,
) -> dict[str, Any]:
    """White-style max-performance reality check using a moving-block bootstrap.

    Inputs are benchmark loss minus candidate loss, so positive values mean the candidate
    outperformed the benchmark. Bootstrap samples use null-centered differentials.
    """
    names, n = _require_series(loss_differentials)
    if bootstrap_samples < 100:
        raise InferenceError("bootstrap_samples must be at least 100")
    means = {name: _mean([float(value) for value in loss_differentials[name]]) for name in names}
    observed = max(math.sqrt(n) * means[name] for name in names)
    centered = {
        name: [float(value) - means[name] for value in loss_differentials[name]]
        for name in names
    }
    rng = random.Random(seed)
    bootstrap: list[float] = []
    for _ in range(bootstrap_samples):
        indices = _moving_block_indices(n, block_length, rng)
        statistic = max(
            math.sqrt(n) * _mean([centered[name][index] for index in indices])
            for name in names
        )
        bootstrap.append(statistic)
    winner = max(names, key=means.__getitem__)
    return {
        "procedure": "white_reality_check",
        "implementation": "moving_block_bootstrap_max_centered_mean",
        "observations": n,
        "family_size": len(names),
        "block_length": block_length,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "observed_statistic": observed,
        "p_value": _bootstrap_pvalue(observed, bootstrap),
        "best_candidate": winner,
        "mean_loss_differential": means[winner],
        "inputs_sha256": _inputs_sha256(loss_differentials),
    }


def hansen_spa(
    loss_differentials: dict[str, list[float]],
    *,
    bootstrap_samples: int = 2000,
    block_length: int = 5,
    seed: int = 0,
) -> dict[str, Any]:
    """Studentized superior-predictive-ability test with moving-block bootstrap."""
    names, n = _require_series(loss_differentials)
    if bootstrap_samples < 100:
        raise InferenceError("bootstrap_samples must be at least 100")
    series = {name: [float(value) for value in loss_differentials[name]] for name in names}
    means = {name: _mean(series[name]) for name in names}
    scales = {name: max(_sample_std(series[name]), 1e-12) for name in names}
    observed_by_name = {
        name: math.sqrt(n) * max(means[name], 0.0) / scales[name]
        for name in names
    }
    observed = max(observed_by_name.values())
    centered = {name: [value - means[name] for value in series[name]] for name in names}
    rng = random.Random(seed)
    bootstrap: list[float] = []
    for _ in range(bootstrap_samples):
        indices = _moving_block_indices(n, block_length, rng)
        statistic = max(
            math.sqrt(n)
            * max(_mean([centered[name][index] for index in indices]), 0.0)
            / scales[name]
            for name in names
        )
        bootstrap.append(statistic)
    winner = max(names, key=observed_by_name.__getitem__)
    return {
        "procedure": "hansen_spa",
        "implementation": "studentized_moving_block_bootstrap",
        "observations": n,
        "family_size": len(names),
        "block_length": block_length,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "observed_statistic": observed,
        "p_value": _bootstrap_pvalue(observed, bootstrap),
        "best_candidate": winner,
        "candidate_statistics": observed_by_name,
        "inputs_sha256": _inputs_sha256(loss_differentials),
    }


def model_confidence_set(
    losses: dict[str, list[float]],
    *,
    alpha: float = 0.05,
    bootstrap_samples: int = 2000,
    block_length: int = 5,
    seed: int = 0,
) -> dict[str, Any]:
    """Iterative loss-based model confidence set using moving-block bootstrap tests."""
    names, n = _require_series(losses)
    if not 0 < alpha < 1:
        raise InferenceError("alpha must be inside (0, 1)")
    if bootstrap_samples < 100:
        raise InferenceError("bootstrap_samples must be at least 100")
    numeric = {name: [float(value) for value in losses[name]] for name in names}
    active = list(names)
    eliminations: list[dict[str, Any]] = []
    rng = random.Random(seed)
    while len(active) > 1:
        means = {name: _mean(numeric[name]) for name in active}
        grand = _mean(list(means.values()))
        observed = max(math.sqrt(n) * abs(means[name] - grand) for name in active)
        centered = {
            name: [value - means[name] for value in numeric[name]]
            for name in active
        }
        bootstrap: list[float] = []
        for _ in range(bootstrap_samples):
            indices = _moving_block_indices(n, block_length, rng)
            boot_means = {
                name: _mean([centered[name][index] for index in indices])
                for name in active
            }
            boot_grand = _mean(list(boot_means.values()))
            bootstrap.append(
                max(math.sqrt(n) * abs(boot_means[name] - boot_grand) for name in active)
            )
        p_value = _bootstrap_pvalue(observed, bootstrap)
        if p_value > alpha:
            break
        removed = max(active, key=means.__getitem__)
        eliminations.append({"model": removed, "p_value": p_value, "mean_loss": means[removed]})
        active.remove(removed)
    return {
        "procedure": "model_confidence_set",
        "implementation": "iterative_moving_block_bootstrap_loss_set",
        "alpha": alpha,
        "observations": n,
        "initial_family_size": len(names),
        "block_length": block_length,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "included_models": sorted(active),
        "eliminations": eliminations,
        "inputs_sha256": _inputs_sha256(losses),
    }


def validate_family_inference_record(record: dict[str, Any]) -> None:
    family_id = record.get("family_id")
    if not isinstance(family_id, str) or not family_id:
        raise InferenceError("family inference requires family_id")
    procedure = record.get("procedure")
    if procedure not in SUPPORTED_PROCEDURES:
        raise InferenceError(f"unsupported family inference procedure: {procedure!r}")
    sha = record.get("inputs_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        raise InferenceError("family inference requires inputs_sha256")
    implementation = record.get("implementation_ref")
    if not isinstance(implementation, str) or not implementation:
        raise InferenceError("family inference requires implementation_ref")
    if not isinstance(record.get("result"), dict):
        raise InferenceError("family inference requires structured result")
    if procedure == "justified_alternative":
        justification = record.get("justification")
        if not isinstance(justification, str) or not justification.strip():
            raise InferenceError("justified alternative requires justification")
