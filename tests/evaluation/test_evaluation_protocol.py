import numpy as np
import pytest


def test_direction_probability_scores_are_proper_and_thresholded() -> None:
    from commodity.evaluation_protocol import evaluate_direction_probabilities

    actual = np.array([0.02, -0.01, 0.03, -0.04])
    probability = np.array([0.9, 0.1, 0.8, 0.2])

    result = evaluate_direction_probabilities(actual, probability)

    assert result["n"] == 4.0
    assert result["direction_accuracy"] == 1.0
    assert result["brier_score"] == pytest.approx(0.025)
    assert result["log_loss"] > 0.0
    assert result["observed_up_rate"] == 0.5
    assert result["mean_predicted_up_probability"] == 0.5


def test_direction_probability_scores_reject_invalid_probabilities() -> None:
    from commodity.evaluation_protocol import evaluate_direction_probabilities

    with pytest.raises(ValueError, match="between 0 and 1"):
        evaluate_direction_probabilities([0.1, -0.1], [1.1, 0.2])


def test_gaussian_volatility_scores_include_scale_error_and_log_score() -> None:
    from commodity.evaluation_protocol import evaluate_zero_mean_gaussian_volatility

    actual = np.array([0.01, -0.02, 0.03])
    sigma = np.array([0.02, 0.02, 0.02])

    result = evaluate_zero_mean_gaussian_volatility(actual, sigma)

    expected_nll = np.mean(
        0.5 * np.log(2.0 * np.pi * sigma**2) + 0.5 * (actual / sigma) ** 2
    )
    assert result["n"] == 3.0
    assert result["volatility_mae"] == pytest.approx(0.006666666666666667)
    assert result["volatility_rmse"] == pytest.approx(np.sqrt(2.0 / 30000.0))
    assert result["gaussian_nll"] == pytest.approx(expected_nll)


def test_gaussian_volatility_scores_fail_closed_on_invalid_scale() -> None:
    from commodity.evaluation_protocol import evaluate_zero_mean_gaussian_volatility

    with pytest.raises(ValueError, match="strictly positive"):
        evaluate_zero_mean_gaussian_volatility([0.01, -0.02], [0.02, 0.0])


def test_benjamini_hochberg_adjustment_is_monotone_and_bounded() -> None:
    from commodity.evaluation_protocol import benjamini_hochberg_adjust

    p_values = [0.01, 0.04, 0.03, 0.20]
    adjusted = benjamini_hochberg_adjust(p_values)

    assert adjusted == pytest.approx([0.04, 0.05333333333333334, 0.05333333333333334, 0.20])
    sorted_pairs = sorted(zip(p_values, adjusted, strict=True))
    assert [adjusted_p for _, adjusted_p in sorted_pairs] == sorted(
        adjusted_p for _, adjusted_p in sorted_pairs
    )
    assert all(0.0 <= value <= 1.0 for value in adjusted)


def test_benjamini_hochberg_adjustment_handles_empty_and_singleton_inputs() -> None:
    from commodity.evaluation_protocol import benjamini_hochberg_adjust

    assert benjamini_hochberg_adjust([]) == []
    assert benjamini_hochberg_adjust([0.25]) == [0.25]

    with pytest.raises(ValueError, match="between 0 and 1"):
        benjamini_hochberg_adjust([0.1, -0.2])
