from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

FORBIDDEN_COLUMNS = frozenset(
    {
        "target",
        "target_ret_1",
        "realized_return",
        "realized_pnl",
        "pnl",
        "future_settle",
    }
)


@dataclass(frozen=True)
class SpecialistIdentity:
    name: str
    model_id: str
    model_revision: str
    checkpoint_sha256: str
    pretraining_exposure: str
    license_status: str

    def validate(self) -> None:
        fields = (self.name, self.model_id, self.model_revision, self.checkpoint_sha256)
        if any(not str(value).strip() for value in fields):
            raise ValueError("specialist identity is incomplete")
        if self.license_status != "verified_for_research_use":
            raise ValueError("specialist license is not verified for research use")
        allowed = {"not_proven_pre_target", "known_pre_target"}
        if self.pretraining_exposure not in allowed:
            raise ValueError("pretraining exposure status is not explicit")


def _as_utc(series: pd.Series) -> pd.Series:
    values = pd.to_datetime(series, utc=True, errors="raise", format="mixed")
    if values.isna().any():
        raise ValueError("timestamp column contains missing values")
    return values

def validate_specialist_features(
    frame: pd.DataFrame,
    *,
    identity: SpecialistIdentity,
    feature_columns: Sequence[str],
) -> pd.DataFrame:
    identity.validate()
    required = {"prediction_time", "generated_at", "contract_id", *feature_columns}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"specialist frame missing columns: {missing}")
    forbidden = sorted(FORBIDDEN_COLUMNS.intersection(frame.columns))
    if forbidden:
        raise ValueError(f"specialist frame contains target leakage columns: {forbidden}")

    checked = frame.copy()
    checked["prediction_time"] = _as_utc(checked["prediction_time"])
    checked["generated_at"] = _as_utc(checked["generated_at"])
    if (checked["generated_at"] > checked["prediction_time"]).any():
        raise ValueError("specialist output was generated after its prediction cutoff")
    if checked["contract_id"].isna().any():
        raise ValueError("specialist frame contains missing contract identity")
    if checked[list(feature_columns)].isna().any().any():
        raise ValueError("specialist features contain missing values")
    return checked

def merge_specialist_features(
    market: pd.DataFrame,
    specialist: pd.DataFrame,
    *,
    identity: SpecialistIdentity,
    feature_columns: Sequence[str],
) -> pd.DataFrame:
    checked = validate_specialist_features(
        specialist, identity=identity, feature_columns=feature_columns
    )
    keys = ["prediction_time", "contract_id"]
    if checked.duplicated(keys).any():
        raise ValueError("specialist features are not unique at the PIT join grain")
    market_checked = market.copy()
    market_checked["prediction_time"] = _as_utc(market_checked["prediction_time"])
    merged = market_checked.merge(
        checked[keys + list(feature_columns)],
        on=keys,
        how="left",
        validate="many_to_one",
    )
    if merged[list(feature_columns)].isna().any().any():
        raise ValueError("specialist feature coverage is incomplete")
    return merged


def probabilistic_interval_diagnostics(
    *,
    actual: pd.Series,
    lower: pd.Series,
    upper: pd.Series,
    lower_quantile: float,
    upper_quantile: float,
) -> dict[str, float | int]:
    if not 0.0 < lower_quantile < upper_quantile < 1.0:
        raise ValueError("quantile bounds must satisfy 0 < lower < upper < 1")
    frame = pd.DataFrame({"actual": actual, "lower": lower, "upper": upper}).astype(float)
    if frame.empty or frame.isna().any().any():
        raise ValueError("probabilistic diagnostics require complete non-empty inputs")
    if (frame["lower"] > frame["upper"]).any():
        raise ValueError("probabilistic interval has crossed quantiles")

    below = frame["actual"] < frame["lower"]
    above = frame["actual"] > frame["upper"]
    covered = ~(below | above)
    lower_hits = frame["actual"] <= frame["lower"]
    upper_hits = frame["actual"] <= frame["upper"]
    nominal = upper_quantile - lower_quantile
    empirical = float(covered.mean())
    lower_rate = float(lower_hits.mean())
    upper_rate = float(upper_hits.mean())
    return {
        "rows": len(frame),
        "nominal_coverage": float(nominal),
        "empirical_coverage": empirical,
        "coverage_error": empirical - float(nominal),
        "lower_hit_rate": lower_rate,
        "lower_calibration_error": lower_rate - lower_quantile,
        "upper_hit_rate": upper_rate,
        "upper_calibration_error": upper_rate - upper_quantile,
        "below_interval_rate": float(below.mean()),
        "above_interval_rate": float(above.mean()),
        "mean_interval_width": float((frame["upper"] - frame["lower"]).mean()),
    }


def remove_one_component_sets(components: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
    ordered = tuple(dict.fromkeys(components))
    return {name: tuple(value for value in ordered if value != name) for name in ordered}
