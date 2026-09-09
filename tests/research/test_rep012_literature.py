from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commodity.rep012_literature import (
    estimate_roberts_henry_hub_equation,
    estimate_roberts_johansen,
    load_roberts_frame,
    sample_mask,
)

RAW_DATA = (
    Path(__file__).resolve().parents[2]
    / "data/raw/snapshots/iree/roberts-2019-revisiting-drivers/resources/brownyuceldata.dta"
)


def _roberts_frame() -> pd.DataFrame:
    if not RAW_DATA.exists():
        pytest.skip("governed ignored Roberts snapshot is not present")
    return load_roberts_frame(RAW_DATA)


def test_roberts_sample_contract() -> None:
    frame = _roberts_frame()
    assert len(frame) == 1045
    assert sample_mask(frame, "brown_yucel").sum() == 522
    assert sample_mask(frame, "post_2007").sum() == 523
    assert frame.loc[sample_mask(frame, "brown_yucel"), "date_dt"].max().date().isoformat() == "2007-06-08"
    assert frame.loc[sample_mask(frame, "post_2007"), "date_dt"].min().date().isoformat() == "2007-06-15"


def test_table3_replication_without_exogenous_controls() -> None:
    result = estimate_roberts_johansen(
        _roberts_frame(), "brown_yucel", with_exogenous=False
    )
    assert result.effective_rows == 517
    np.testing.assert_allclose(result.eigenvalues, [0.02998, 0.00089], atol=5e-6)
    np.testing.assert_allclose(result.trace_statistics, [16.1921, 0.4579], atol=5e-5)
    np.testing.assert_allclose(result.max_eigen_statistics, [15.7342, 0.4579], atol=5e-5)
    assert result.beta[1] == pytest.approx(-0.9467, abs=5e-5)
    assert result.beta_se_wti == pytest.approx(0.1182, abs=5e-5)
    np.testing.assert_allclose(result.alpha, [-0.0590, 0.0046], atol=5e-5)
    np.testing.assert_allclose(result.alpha_se, [0.0156, 0.0080], atol=5e-5)
    assert result.rank_at_5pct == 1
    assert result.rank_at_1pct == 0


def test_table3_replication_with_stationary_controls() -> None:
    result = estimate_roberts_johansen(
        _roberts_frame(), "brown_yucel", with_exogenous=True
    )
    np.testing.assert_allclose(result.eigenvalues, [0.0646, 0.0012], atol=5e-5)
    np.testing.assert_allclose(result.trace_statistics, [35.163, 0.6387], atol=5e-4)
    np.testing.assert_allclose(result.max_eigen_statistics, [34.524, 0.6387], atol=5e-4)
    assert result.beta[1] == pytest.approx(-0.9118, abs=5e-5)
    assert result.beta_se_wti == pytest.approx(0.0680, abs=5e-5)
    np.testing.assert_allclose(result.alpha, [-0.1074, 0.0176], atol=5e-5)
    np.testing.assert_allclose(result.alpha_se, [0.020, 0.011], atol=5e-4)
    assert result.rank_at_1pct == 1


def test_full_and_post_samples_reproduce_cointegration_break() -> None:
    frame = _roberts_frame()
    expected = {
        ("full", False): ([10.8701, 3.1385], [7.7316, 3.1385], -0.3108),
        ("full", True): ([10.5459, 3.449], [7.0968, 3.449], -0.4447),
        ("post_2007", False): ([12.6657, 2.0077], [10.6580, 2.0077], -1.0520),
        ("post_2007", True): ([12.4583, 0.0640], [12.3943, 0.0640], -1.2818),
    }
    for (sample, with_exogenous), (trace, maximum, beta_wti) in expected.items():
        result = estimate_roberts_johansen(
            frame, sample, with_exogenous=with_exogenous
        )
        np.testing.assert_allclose(result.trace_statistics, trace, atol=5e-4)
        np.testing.assert_allclose(result.max_eigen_statistics, maximum, atol=5e-4)
        assert result.beta[1] == pytest.approx(beta_wti, abs=5e-5)
        assert result.rank_at_5pct == 0


def test_post_sample_uses_pre_boundary_lag_context_like_stata_if() -> None:
    result = estimate_roberts_johansen(
        _roberts_frame(), "post_2007", with_exogenous=False
    )
    # Stata evaluates time-series lags before applying the if qualifier. All 523
    # post-sample current observations therefore remain estimable using earlier lag context.
    assert result.input_rows == 523
    assert result.effective_rows == 523


def test_table6_henry_hub_equation_without_controls() -> None:
    result = estimate_roberts_henry_hub_equation(
        _roberts_frame(), with_exogenous=False
    )
    expected = {
        "error_correction": -0.0590,
        "dln_wti_l1": 0.0686,
        "dln_wti_l2": -0.1241,
        "dln_wti_l3": -0.0229,
        "dln_wti_l4": -0.0598,
        "dln_hh_l1": 0.1501,
        "dln_hh_l2": -0.0244,
        "dln_hh_l3": 0.0070,
        "dln_hh_l4": -0.0861,
    }
    for name, value in expected.items():
        assert result.coefficients[name] == pytest.approx(value, abs=5e-5)
    assert result.z_statistics["error_correction"] == pytest.approx(-3.78, abs=0.01)
    assert result.residual_standard_error == pytest.approx(0.081, abs=5e-4)


def test_table6_physical_controls_reproduce_roberts() -> None:
    result = estimate_roberts_henry_hub_equation(
        _roberts_frame(), with_exogenous=True
    )
    expected = {
        "hdds": (8.34e-5, 1.02),
        "dev_hdds": (9.11e-4, 4.84),
        "cdds": (-2.63e-4, -1.10),
        "dev_cdds": (3.00e-3, 4.64),
        "stor_diff": (-4.39e-5, -2.66),
        "hurr_shutin_bcf": (4.47e-4, 0.63),
    }
    for name, (coefficient, z_statistic) in expected.items():
        assert result.coefficients[name] == pytest.approx(coefficient, abs=5e-6)
        assert result.z_statistics[name] == pytest.approx(z_statistic, abs=0.01)
    assert result.coefficients["error_correction"] == pytest.approx(-0.1074, abs=5e-5)
    assert result.z_statistics["error_correction"] == pytest.approx(-5.31, abs=0.01)
    assert result.residual_standard_error == pytest.approx(0.077, abs=5e-4)
