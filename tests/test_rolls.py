import pandas as pd
import pytest

from commodity import rolls
from commodity.config import assumptions_config, data_config
from commodity.market_data import DataContractViolation
from commodity.rolls import build_derived_contract_path, within_contract_log_returns


def _contracts() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-01-05", periods=4, freq="D", tz="UTC")
    liquidity = [
        ((100, 100), (50, 50)),
        ((90, 90), (120, 110)),
        ((80, 80), (130, 120)),
        ((70, 70), (140, 130)),
    ]
    for date, pair in zip(dates, liquidity, strict=True):
        rows.extend([
            {"trade_date": date, "contract_id": "NGF26", "expiration": "2026-01-20", "settle": 3.0, "volume": pair[0][0], "open_interest": pair[0][1]},
            {"trade_date": date, "contract_id": "NGG26", "expiration": "2026-02-20", "settle": 3.2 + 0.01 * len(rows), "volume": pair[1][0], "open_interest": pair[1][1]},
        ])
    return pd.DataFrame(rows)


def _policy() -> dict:
    return {"method": "dual_liquidity_crossover", "confirmation_sessions": 1, "forced_roll_days_before_expiry": 0}


def test_roll_policy_has_no_hidden_defaults() -> None:
    with pytest.raises(ValueError, match="missing explicit fields"):
        build_derived_contract_path(_contracts(), data_config()["canonical_contract_schema"], {"method": "dual_liquidity_crossover"})


def test_roll_uses_prior_session_volume_and_open_interest() -> None:
    path = build_derived_contract_path(
        _contracts(), data_config()["canonical_contract_schema"], _policy()
    )
    assert list(path["contract_id"]) == ["NGF26", "NGF26", "NGG26", "NGG26"]
    assert path.iloc[2]["roll_reason"] == "prior_session_dual_liquidity"


def test_returns_are_blank_across_roll_boundary() -> None:
    path = build_derived_contract_path(
        _contracts(), data_config()["canonical_contract_schema"], _policy()
    )
    returns = within_contract_log_returns(path)
    assert pd.isna(returns.iloc[0])
    assert pd.notna(returns.iloc[1])
    assert pd.isna(returns.iloc[2])
    assert pd.notna(returns.iloc[3])


def _volume_policy() -> dict:
    return dict(
        assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    )


def _volume_contracts(
    dates: list[str],
    front_volumes: list[float | None],
    next_volumes: list[float | None],
    front_expiration: str = "2026-01-20",
) -> pd.DataFrame:
    rows = []
    for date, front_volume, next_volume in zip(
        dates, front_volumes, next_volumes, strict=True
    ):
        rows.extend([
            {"trade_date": date, "contract_id": "NGF26", "expiration": front_expiration,
             "settle": 3.0, "volume": front_volume},
            {"trade_date": date, "contract_id": "NGG26", "expiration": "2026-02-20",
             "settle": 3.2, "volume": next_volume},
        ])
    return pd.DataFrame(rows)


def test_volume_roll_requires_two_prior_observed_session_crossovers() -> None:
    frame = _volume_contracts(
        ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        [100, 90, 80, 70],
        [80, 110, 120, 130],
    )
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert list(path["contract_id"]) == ["NGF26", "NGF26", "NGF26", "NGG26"]
    row = ledger.iloc[0]
    assert row["trigger"] == "prior_session_volume_crossover"
    assert row["old_contract"] == "NGF26"
    assert row["new_contract"] == "NGG26"
    assert row["old_contract_dte"] == 12
    assert row["prior_current_volume"] == 80
    assert row["prior_next_volume"] == 120
    assert row["confirmation_count"] == 2


@pytest.mark.parametrize("reset_value", [100, None], ids=["tie", "missing"])
def test_volume_roll_tie_or_missing_volume_resets_confirmation(reset_value) -> None:
    frame = _volume_contracts(
        ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"],
        [100, 90, 100, 80, 70],
        [80, 110, reset_value, 120, 130],
    )
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert list(path["contract_id"]) == ["NGF26"] * 5
    assert ledger.empty


def test_volume_roll_forces_at_three_calendar_dte() -> None:
    frame = _volume_contracts(
        ["2026-01-16", "2026-01-17"], [100, 100], [50, 50]
    )
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert list(path["contract_id"]) == ["NGF26", "NGG26"]
    assert ledger.iloc[0]["trigger"] == "forced_dte"
    assert ledger.iloc[0]["old_contract_dte"] == 3


def test_volume_roll_counts_observed_sessions_across_calendar_gap() -> None:
    frame = _volume_contracts(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"],
        [100, 90, 80, 70],
        [80, 110, 120, 130],
    )
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert path.iloc[-1]["contract_id"] == "NGG26"
    assert ledger.iloc[0]["trade_date"] == pd.Timestamp("2026-01-07", tz="UTC")


def test_volume_roll_advances_when_current_contract_is_unavailable() -> None:
    frame = pd.DataFrame([
        {"trade_date": "2026-01-05", "contract_id": "NGF26", "expiration": "2026-01-20", "settle": 3.0, "volume": 100},
        {"trade_date": "2026-01-05", "contract_id": "NGG26", "expiration": "2026-02-20", "settle": 3.2, "volume": 80},
        {"trade_date": "2026-01-06", "contract_id": "NGG26", "expiration": "2026-02-20", "settle": 3.3, "volume": 90},
    ])
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert list(path["contract_id"]) == ["NGF26", "NGG26"]
    assert ledger.iloc[0]["trigger"] == "contract_unavailable"


def test_volume_roll_fails_closed_when_current_disappears_without_later_contract() -> None:
    frame = pd.DataFrame([
        {"trade_date": "2026-01-05", "contract_id": "NGF26", "expiration": "2026-01-20", "settle": 3.0, "volume": 100},
        {"trade_date": "2026-01-06", "contract_id": "NGE26", "expiration": "2026-01-15", "settle": 2.9, "volume": 50},
    ])
    with pytest.raises(DataContractViolation, match="no later eligible contract"):
        rolls.build_derived_continuous_series(
            frame, data_config()["canonical_contract_schema"], _volume_policy()
        )


def test_continuous_series_never_returns_across_contract_boundary() -> None:
    frame = _volume_contracts(
        ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        [100, 90, 80, 70],
        [80, 110, 120, 130],
    )
    path, _ = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    returns = path["settle_log_return"]
    assert pd.isna(returns.iloc[0])
    assert pd.notna(returns.iloc[1])
    assert pd.notna(returns.iloc[2])
    assert pd.isna(returns.iloc[3])


def test_volume_roll_applies_dte_guard_on_initial_session() -> None:
    frame = _volume_contracts(
        ["2026-01-17"], [100], [50]
    )
    path, ledger = rolls.build_derived_continuous_series(
        frame, data_config()["canonical_contract_schema"], _volume_policy()
    )
    assert list(path["contract_id"]) == ["NGG26"]
    assert path.iloc[0]["roll_reason"] == "forced_dte"
    assert ledger.iloc[0]["old_contract"] == "NGF26"
    assert ledger.iloc[0]["new_contract"] == "NGG26"
    assert ledger.iloc[0]["trigger"] == "forced_dte"
    assert ledger.iloc[0]["old_contract_dte"] == 3
    assert pd.isna(path.iloc[0]["settle_log_return"])


def test_volume_roll_requires_every_declared_semantic() -> None:
    policy = _volume_policy()
    policy.pop("tie_behavior")
    with pytest.raises(ValueError, match="tie_behavior"):
        rolls.build_derived_continuous_series(
            _volume_contracts(["2026-01-05"], [100], [80]),
            data_config()["canonical_contract_schema"],
            policy,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("volume_evidence", "same_session"),
        ("crossover", "greater_than_or_equal"),
        ("tie_behavior", "hold_without_reset"),
        ("missing_volume_behavior", "ignore"),
        ("holiday_behavior", "calendar_days"),
        ("contract_unavailable_behavior", "hold_missing"),
        ("no_later_contract_behavior", "reuse_expired"),
    ],
)
def test_volume_roll_rejects_unsupported_declared_semantics(field, value) -> None:
    policy = _volume_policy()
    policy[field] = value
    with pytest.raises(ValueError, match=field):
        rolls.build_derived_continuous_series(
            _volume_contracts(["2026-01-05"], [100], [80]),
            data_config()["canonical_contract_schema"],
            policy,
        )
