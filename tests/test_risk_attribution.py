"""Tests for risk attribution and decomposition functions."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from quant_trading.risk.metrics import (
    calculate_component_var,
    calculate_cvar,
    calculate_equal_risk_contribution_weights,
    calculate_marginal_var,
    calculate_risk_budget_weights,
    calculate_var,
    calculate_volatility,
    calculate_volatility_contributions,
)


class TestMarginalVaR:
    """Tests for calculate_marginal_var."""

    def test_marginal_var_basic(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        assert len(mvar) == 2
        assert mvar.index.tolist() == ["A", "B"]
        assert np.isfinite(mvar.values).all()

    def test_marginal_var_single_asset(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame({"A": np.random.normal(0.001, 0.02, 200)})
        weights = pd.Series([1.0], index=["A"])
        mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        assert len(mvar) == 1
        assert mvar.index.tolist() == ["A"]

    def test_marginal_var_insufficient_data(self) -> None:
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        mvar = calculate_marginal_var(returns, weights)
        assert len(mvar) == 2
        assert (mvar == 0.0).all()

    def test_marginal_var_invalid_weights_sum(self) -> None:
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.3, 0.3], index=["A", "B"])
        with pytest.raises(ValueError, match="sum to 1.0"):
            calculate_marginal_var(returns, weights)

    def test_marginal_var_nan_weights(self) -> None:
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.5, np.nan], index=["A", "B"])
        with pytest.raises(ValueError, match="finite"):
            calculate_marginal_var(returns, weights)

    def test_marginal_var_empty_tail_returns_zeros(self) -> None:
        # Force an empty tail: portfolio returns contain NaN (inf - inf
        # cancellation), so np.percentile returns NaN and every
        # `portfolio_returns <= -var_threshold` comparison is False.
        returns = pd.DataFrame({"A": [np.inf, 1.0], "B": [-np.inf, 1.0]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        with np.errstate(invalid="ignore"):
            mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        assert len(mvar) == 2
        assert mvar.index.tolist() == ["A", "B"]
        assert (mvar == 0.0).all()


class TestComponentVaR:
    """Tests for calculate_component_var."""

    def test_component_var_basic(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        cvar = calculate_component_var(returns, weights, confidence=0.95)
        assert len(cvar) == 2
        assert cvar.index.tolist() == ["A", "B"]
        assert np.isfinite(cvar.values).all()

    def test_component_var_sums_to_portfolio_var(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
                "C": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = pd.Series([0.4, 0.3, 0.3], index=["A", "B", "C"])
        cvar = calculate_component_var(returns, weights, confidence=0.95)

        portfolio_returns = pd.Series(returns.values @ weights.values)
        portfolio_cvar = calculate_cvar(portfolio_returns, 0.95)

        # The component VaRs are negative losses and their sum equals the
        # portfolio Expected Shortfall (CVaR), not the quantile-based VaR.
        assert abs(cvar.sum() - portfolio_cvar) < 1e-6

    def test_component_var_single_asset(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame({"A": np.random.normal(0.001, 0.02, 200)})
        weights = pd.Series([1.0], index=["A"])
        cvar = calculate_component_var(returns, weights, confidence=0.95)
        assert len(cvar) == 1
        assert cvar.index.tolist() == ["A"]

    def test_component_var_sign_is_negative_loss(self) -> None:
        """Component VaR is a negative loss, consistent with ``calculate_var``.

        The historical-simulation marginal VaR is the mean asset return in the
        tail of the portfolio distribution, so for a long-only portfolio the
        component VaRs are negative. Their sum equals the portfolio Expected
        Shortfall (CVaR), not the quantile-based VaR.
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
                "C": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = pd.Series([0.4, 0.3, 0.3], index=["A", "B", "C"])
        cvar = calculate_component_var(returns, weights, confidence=0.95)

        assert (cvar <= 0).all(), "component VaR must be a negative loss"

        portfolio_returns = pd.Series(returns.values @ weights.values)
        portfolio_var = calculate_var(portfolio_returns, 0.95)
        portfolio_cvar = calculate_cvar(portfolio_returns, 0.95)

        # The component sum tracks the tail mean (CVaR), not the quantile.
        assert abs(cvar.sum() - portfolio_cvar) < 1e-6
        assert abs(cvar.sum() - portfolio_var) > abs(portfolio_var) * 0.1


class TestVolatilityContributions:
    """Tests for calculate_volatility_contributions."""

    def test_vol_contrib_basic(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert len(contrib) == 2
        assert contrib.index.tolist() == ["A", "B"]
        assert np.isfinite(contrib.values).all()

    def test_vol_contrib_sums_to_portfolio_vol(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
                "C": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = pd.Series([0.4, 0.3, 0.3], index=["A", "B", "C"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)

        portfolio_returns = pd.Series(returns.values @ weights.values)
        portfolio_vol = calculate_volatility(portfolio_returns, annualize=False)

        assert abs(contrib.sum() - portfolio_vol) < 1e-6

    def test_vol_contrib_annualized(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=True)
        assert np.isfinite(contrib.values).all()

    def test_vol_contrib_insufficient_data(self) -> None:
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert (contrib == 0.0).all()

    def test_vol_contrib_invalid_weights(self) -> None:
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.3, 0.3], index=["A", "B"])
        with pytest.raises(ValueError, match="sum to 1.0"):
            calculate_volatility_contributions(returns, weights)

    def test_vol_contrib_zero_portfolio_variance(self) -> None:
        """Constant returns give zero covariance -> zero contributions.

        When every asset return is constant the covariance matrix is all zeros,
        so ``portfolio_variance`` is 0 and the guard returns a zero series
        (quant_trading/risk/metrics.py:calculate_volatility_contributions).
        """
        returns = pd.DataFrame({"A": [0.001, 0.001, 0.001], "B": [0.002, 0.002, 0.002]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert contrib.index.tolist() == ["A", "B"]
        assert (contrib == 0.0).all()


class TestEqualRiskContribution:
    """Tests for calculate_equal_risk_contribution_weights."""

    def test_erc_basic(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 2
        assert weights.index.tolist() == ["A", "B"]
        assert abs(weights.sum() - 1.0) < 1e-6
        assert (weights >= 0).all()

    def test_erc_equal_contributions(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert abs(contrib["A"] - contrib["B"]) < contrib.sum() * 0.05

    def test_erc_three_assets(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
                "C": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 3
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_erc_insufficient_data(self) -> None:
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_erc_empty_returns(self) -> None:
        returns = pd.DataFrame()
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 0 or abs(weights.sum() - 1.0) < 1e-6

    def test_erc_zero_variance_returns(self) -> None:
        """Zero target contribution stops the iteration and keeps initial weights.

        Constant returns make every volatility contribution zero, so the target
        contribution is zero and the loop breaks before rescaling
        (quant_trading/risk/metrics.py:calculate_equal_risk_contribution_weights).
        """
        returns = pd.DataFrame({"A": [0.001, 0.001, 0.001], "B": [0.002, 0.002, 0.002]})
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert weights.index.tolist() == ["A", "B"]
        np.testing.assert_allclose(weights.to_numpy(), [0.5, 0.5])

    def test_erc_max_iter_one_runs_single_pass(self) -> None:
        """A single iteration exhausts the loop and returns normalized weights.

        With ``max_iter=1`` the loop cannot converge, so execution falls through
        to the final return instead of the convergence break
        (quant_trading/risk/metrics.py:calculate_equal_risk_contribution_weights).
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        weights = calculate_equal_risk_contribution_weights(returns, max_iter=1, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6
        assert np.isfinite(weights.to_numpy()).all()

    def test_erc_long_only_clamps_weights(self) -> None:
        """The long_only clamp keeps ERC weights non-negative and normalized.

        Exercises the long_only clamp branch (quant_trading/risk/metrics.py:867).
        The weight_sum guard's break (quant_trading/risk/metrics.py:870-871) is
        covered separately by
        ``test_erc_canceling_contributions_stop_iteration``: the guard is
        reachable when mixed-sign (long/short) risk contributions cancel the
        rescaled weights to exactly zero.
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.03, 200),
                "C": np.random.normal(0.001, 0.015, 200),
            }
        )
        weights = calculate_equal_risk_contribution_weights(
            returns, long_only=True, annualize=False
        )
        assert len(weights) == 3
        assert weights.index.tolist() == ["A", "B", "C"]
        assert abs(weights.sum() - 1.0) < 1e-6
        assert (weights >= 0).all()
        assert np.isfinite(weights.to_numpy()).all()

    def test_erc_canceling_contributions_stop_iteration(self) -> None:
        """Exactly cancelling scaled weights trigger the weight_sum guard.

        When the rescaled weights sum to exactly zero the iteration cannot
        normalize them, so it stops and returns the weights it has
        (quant_trading/risk/metrics.py:870-871). Mixed-sign risk
        contributions (long/short books) can cancel this way; the degenerate
        contribution series is patched in to make the float-exact
        cancellation deterministic: initial weights (1/3, 1/3, 1/3) scaled by
        target/contrib = (1/2, 1/2, -1) sum to exactly zero.
        """
        returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.01], "C": [0.0, 0.01]})
        degenerate = pd.Series([2.0, 2.0, -1.0], index=["A", "B", "C"])
        with patch(
            "quant_trading.risk.metrics.calculate_volatility_contributions",
            return_value=degenerate,
        ):
            weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert weights.index.tolist() == ["A", "B", "C"]
        np.testing.assert_allclose(weights.to_numpy(), [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
        assert abs(weights.sum() - 1.0) < 1e-6


class TestRiskBudgetWeights:
    """Tests for calculate_risk_budget_weights."""

    def test_risk_budget_basic(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        assert len(weights) == 2
        assert weights.index.tolist() == ["A", "B"]
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_risk_budget_matches_contributions(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
            }
        )
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        actual_budget = contrib / contrib.sum()
        assert abs(actual_budget["A"] - 0.7) < 0.05
        assert abs(actual_budget["B"] - 0.3) < 0.05

    def test_risk_budget_equal_is_erc(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
            }
        )
        budget = pd.Series([0.5, 0.5], index=["A", "B"])
        weights_rb = calculate_risk_budget_weights(returns, budget, annualize=False)
        weights_erc = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert abs(weights_rb["A"] - weights_erc["A"]) < 0.02

    def test_risk_budget_invalid_budget_sum(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        budget = pd.Series([0.5, 0.3], index=["A", "B"])
        with pytest.raises(ValueError, match="sum to 1.0"):
            calculate_risk_budget_weights(returns, budget)

    def test_risk_budget_nan_budget(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        budget = pd.Series([0.5, np.nan], index=["A", "B"])
        with pytest.raises(ValueError, match="finite"):
            calculate_risk_budget_weights(returns, budget)

    def test_risk_budget_insufficient_data(self) -> None:
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_risk_budget_zero_variance_returns(self) -> None:
        """Zero total contribution stops the iteration and keeps the budget.

        Constant returns make every volatility contribution zero, so the total
        contribution is zero and the loop breaks before rescaling
        (quant_trading/risk/metrics.py:calculate_risk_budget_weights).
        """
        returns = pd.DataFrame({"A": [0.001, 0.001, 0.001], "B": [0.002, 0.002, 0.002]})
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        assert weights.index.tolist() == ["A", "B"]
        np.testing.assert_allclose(weights.to_numpy(), [0.7, 0.3])

    def test_risk_budget_max_iter_one_runs_single_pass(self) -> None:
        """A single iteration exhausts the loop and returns normalized weights.

        With ``max_iter=1`` the loop cannot converge, so execution falls through
        to the final return instead of the convergence break
        (quant_trading/risk/metrics.py:calculate_risk_budget_weights).
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.02, 200),
            }
        )
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, max_iter=1, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6
        assert np.isfinite(weights.to_numpy()).all()

    def test_risk_budget_long_only_clamps_weights(self) -> None:
        """The long_only clamp keeps risk-budget weights non-negative and normalized.

        Exercises the long_only clamp branch (quant_trading/risk/metrics.py:956).
        The weight_sum guard's break (quant_trading/risk/metrics.py:959-960) is
        covered separately by
        ``test_risk_budget_canceling_contributions_stop_iteration``: the guard
        is reachable when mixed-sign (long/short) risk contributions cancel the
        rescaled weights to exactly zero.
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 200),
                "B": np.random.normal(0.001, 0.03, 200),
                "C": np.random.normal(0.001, 0.015, 200),
            }
        )
        budget = pd.Series([0.4, 0.3, 0.3], index=["A", "B", "C"])
        weights = calculate_risk_budget_weights(returns, budget, long_only=True, annualize=False)
        assert len(weights) == 3
        assert weights.index.tolist() == ["A", "B", "C"]
        assert abs(weights.sum() - 1.0) < 1e-6
        assert (weights >= 0).all()
        assert np.isfinite(weights.to_numpy()).all()

    def test_risk_budget_canceling_contributions_stop_iteration(self) -> None:
        """Exactly cancelling scaled weights trigger the weight_sum guard.

        The rescaled weights can sum to exactly zero when risk contributions
        have mixed signs (long/short books); the iteration then stops and
        returns the budget weights unchanged
        (quant_trading/risk/metrics.py:959-960). The degenerate contribution
        series is patched in to make the cancellation deterministic: budget
        (0.5, 0.5, 0.0) rescaled by budget/actual with actual proportional to
        (1, -1, 5) yields (r, -r, 0), which sums to exactly zero.
        """
        returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.02, 0.01], "C": [0.0, 0.01]})
        budget = pd.Series([0.5, 0.5, 0.0], index=["A", "B", "C"])
        degenerate = pd.Series([1.0, -1.0, 5.0], index=["A", "B", "C"])
        with patch(
            "quant_trading.risk.metrics.calculate_volatility_contributions",
            return_value=degenerate,
        ):
            weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        assert weights.index.tolist() == ["A", "B", "C"]
        np.testing.assert_allclose(weights.to_numpy(), [0.5, 0.5, 0.0])


class TestRiskAttributionIntegration:
    """Integration tests for risk attribution functions."""

    def test_risk_package_exports_attribution_api(self) -> None:
        """Risk attribution helpers are part of the public risk package API."""
        from quant_trading import risk

        for name in (
            "calculate_marginal_var",
            "calculate_component_var",
            "calculate_volatility_contributions",
            "calculate_equal_risk_contribution_weights",
            "calculate_risk_budget_weights",
        ):
            assert hasattr(risk, name), f"missing export: {name}"
            assert name in risk.__all__, f"missing from __all__: {name}"
            assert getattr(risk, name) is getattr(
                __import__("quant_trading.risk.metrics", fromlist=[name]), name
            )

    def test_marginal_component_var_consistency(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 500),
                "B": np.random.normal(0.001, 0.02, 500),
            }
        )
        weights = pd.Series([0.6, 0.4], index=["A", "B"])
        mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        cvar = calculate_component_var(returns, weights, confidence=0.95)
        expected_cvar = mvar * weights
        assert abs(cvar["A"] - expected_cvar["A"]) < 1e-6
        assert abs(cvar["B"] - expected_cvar["B"]) < 1e-6

    def test_vol_contrib_with_correlation(self) -> None:
        np.random.seed(42)
        n = 500
        # Create correlated returns
        base = np.random.normal(0.001, 0.02, n)
        returns = pd.DataFrame(
            {
                "A": base + np.random.normal(0, 0.01, n),
                "B": base + np.random.normal(0, 0.01, n),
            }
        )
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert contrib.sum() > 0
        assert np.isfinite(contrib.values).all()

    def test_erc_with_different_volatilities(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.01, 500),  # Low vol
                "B": np.random.normal(0.001, 0.03, 500),  # High vol
            }
        )
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        # Lower vol asset should get higher weight
        assert weights["A"] > weights["B"]
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_risk_budget_with_different_volatilities(self) -> None:
        np.random.seed(42)
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.01, 500),  # Low vol
                "B": np.random.normal(0.001, 0.03, 500),  # High vol
            }
        )
        budget = pd.Series([0.5, 0.5], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        # With equal risk budget, lower vol asset gets higher weight
        assert weights["A"] > weights["B"]
        assert abs(weights.sum() - 1.0) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
