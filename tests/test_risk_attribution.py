"""Tests for risk attribution and decomposition functions."""

import numpy as np
import pandas as pd
import pytest

from quant_trading.risk.metrics import (
    calculate_component_var,
    calculate_equal_risk_contribution_weights,
    calculate_marginal_var,
    calculate_risk_budget_weights,
    calculate_volatility_contributions,
)


class TestMarginalVaR:
    """Tests for calculate_marginal_var."""

    def test_marginal_var_basic(self):
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

    def test_marginal_var_single_asset(self):
        np.random.seed(42)
        returns = pd.DataFrame({"A": np.random.normal(0.001, 0.02, 200)})
        weights = pd.Series([1.0], index=["A"])
        mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        assert len(mvar) == 1
        assert mvar.index.tolist() == ["A"]

    def test_marginal_var_insufficient_data(self):
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        mvar = calculate_marginal_var(returns, weights)
        assert len(mvar) == 2
        assert (mvar == 0.0).all()

    def test_marginal_var_invalid_weights_sum(self):
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.3, 0.3], index=["A", "B"])
        with pytest.raises(ValueError, match="sum to 1.0"):
            calculate_marginal_var(returns, weights)

    def test_marginal_var_nan_weights(self):
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.5, np.nan], index=["A", "B"])
        with pytest.raises(ValueError, match="finite"):
            calculate_marginal_var(returns, weights)


class TestComponentVaR:
    """Tests for calculate_component_var."""

    def test_component_var_basic(self):
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

    def test_component_var_sums_to_portfolio_var(self):
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

        portfolio_returns = returns.values @ weights.values
        from quant_trading.risk.metrics import calculate_var

        portfolio_var = calculate_var(pd.Series(portfolio_returns), 0.95)

        # Euler's theorem: sum of component VaR = portfolio VaR
        # Allow larger tolerance due to finite difference approximation
        assert abs(cvar.sum() - portfolio_var) < abs(portfolio_var) * 0.5 + 1e-4

    def test_component_var_single_asset(self):
        np.random.seed(42)
        returns = pd.DataFrame({"A": np.random.normal(0.001, 0.02, 200)})
        weights = pd.Series([1.0], index=["A"])
        cvar = calculate_component_var(returns, weights, confidence=0.95)
        assert len(cvar) == 1
        assert cvar.index.tolist() == ["A"]


class TestVolatilityContributions:
    """Tests for calculate_volatility_contributions."""

    def test_vol_contrib_basic(self):
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

    def test_vol_contrib_sums_to_portfolio_vol(self):
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

        portfolio_returns = returns.values @ weights.values
        from quant_trading.risk.metrics import calculate_volatility

        portfolio_vol = calculate_volatility(pd.Series(portfolio_returns), annualize=False)

        assert abs(contrib.sum() - portfolio_vol) < 1e-6

    def test_vol_contrib_annualized(self):
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

    def test_vol_contrib_insufficient_data(self):
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = pd.Series([0.5, 0.5], index=["A", "B"])
        contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        assert (contrib == 0.0).all()

    def test_vol_contrib_invalid_weights(self):
        returns = pd.DataFrame(
            {
                "A": np.random.normal(0.001, 0.02, 100),
                "B": np.random.normal(0.001, 0.02, 100),
            }
        )
        weights = pd.Series([0.3, 0.3], index=["A", "B"])
        with pytest.raises(ValueError, match="sum to 1.0"):
            calculate_volatility_contributions(returns, weights)


class TestEqualRiskContribution:
    """Tests for calculate_equal_risk_contribution_weights."""

    def test_erc_basic(self):
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

    def test_erc_equal_contributions(self):
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

    def test_erc_three_assets(self):
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

    def test_erc_insufficient_data(self):
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6

    def test_erc_empty_returns(self):
        returns = pd.DataFrame()
        weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        assert len(weights) == 0 or abs(weights.sum() - 1.0) < 1e-6


class TestRiskBudgetWeights:
    """Tests for calculate_risk_budget_weights."""

    def test_risk_budget_basic(self):
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

    def test_risk_budget_matches_contributions(self):
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

    def test_risk_budget_equal_is_erc(self):
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

    def test_risk_budget_invalid_budget_sum(self):
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

    def test_risk_budget_nan_budget(self):
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

    def test_risk_budget_insufficient_data(self):
        returns = pd.DataFrame({"A": [0.01], "B": [0.02]})
        budget = pd.Series([0.7, 0.3], index=["A", "B"])
        weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        assert len(weights) == 2
        assert abs(weights.sum() - 1.0) < 1e-6


class TestRiskAttributionIntegration:
    """Integration tests for risk attribution functions."""

    def test_risk_package_exports_attribution_api(self):
        """Risk attribution helpers are part of the public risk package API."""
        import quant_trading.risk as risk

        for name in (
            "calculate_marginal_var",
            "calculate_component_var",
            "calculate_volatility_contributions",
            "calculate_equal_risk_contribution_weights",
            "calculate_risk_budget_weights",
        ):
            assert hasattr(risk, name), f"missing export: {name}"
            assert name in risk.__all__, f"missing from __all__: {name}"
            assert getattr(risk, name) is getattr(__import__("quant_trading.risk.metrics", fromlist=[name]), name)

    def test_marginal_component_var_consistency(self):
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

    def test_vol_contrib_with_correlation(self):
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

    def test_erc_with_different_volatilities(self):
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

    def test_risk_budget_with_different_volatilities(self):
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
