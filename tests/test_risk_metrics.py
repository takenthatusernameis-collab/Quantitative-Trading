"""Tests for risk metrics calculation utilities."""

import numpy as np
import pandas as pd
import pytest

from quant_trading.risk.metrics import (
    RiskMetrics,
    calculate_all_metrics,
    calculate_alpha,
    calculate_beta,
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var,
    calculate_volatility,
)

RETURNS = pd.Series([-0.05, -0.02, 0.01, 0.03, 0.08])
MARKET_RETURNS = pd.Series([-0.04, -0.01, 0.02, 0.04, 0.09])
EQUITY_STEADY = pd.Series([100.0, 105.0, 110.0])


class TestCalculateReturns:
    """Tests for calculate_returns."""

    def test_basic_returns(self):
        prices = pd.Series([100.0, 110.0, 121.0])
        expected = pd.Series([0.1, 0.1])
        result = calculate_returns(prices)
        np.testing.assert_allclose(result.values, expected.values)

    def test_single_price_returns_empty(self):
        prices = pd.Series([100.0])
        result = calculate_returns(prices)
        assert len(result) == 0

    def test_empty_prices_returns_empty(self):
        prices = pd.Series([], dtype=float)
        result = calculate_returns(prices)
        assert len(result) == 0

    def test_no_negative_indexing_leak(self):
        prices = pd.Series([100.0, 90.0, 99.0])
        result = calculate_returns(prices)
        assert len(result) == 2


class TestCalculateVolatility:
    """Tests for calculate_volatility."""

    def test_raw_volatility(self):
        vol = calculate_volatility(RETURNS, annualize=False)
        assert vol == pytest.approx(RETURNS.std())

    def test_annualized_volatility(self):
        vol = calculate_volatility(RETURNS, annualize=True)
        assert vol == pytest.approx(RETURNS.std() * np.sqrt(252))

    def test_annualized_scales_raw(self):
        raw = calculate_volatility(RETURNS, annualize=False)
        annual = calculate_volatility(RETURNS, annualize=True)
        assert annual == pytest.approx(raw * np.sqrt(252))

    def test_empty_series_returns_zero(self):
        """Empty returns must not propagate NaN (risk/metrics.py:44->47)."""
        result = calculate_volatility(pd.Series([], dtype=float))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_empty_series_non_annualized_returns_zero(self):
        """Empty returns must not propagate NaN when annualize=False."""
        result = calculate_volatility(pd.Series([], dtype=float), annualize=False)
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_single_value_zero(self):
        """A single return has undefined std; must not propagate NaN."""
        result = calculate_volatility(pd.Series([0.01]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)


class TestCalculateMaxDrawdown:
    """Tests for calculate_max_drawdown."""

    def test_drawdown_from_peak(self):
        equity = pd.Series([100.0, 110.0, 90.0, 95.0])
        result = calculate_max_drawdown(equity)
        assert result == pytest.approx((90.0 - 110.0) / 110.0)

    def test_no_drawdown_monotonic(self):
        equity = pd.Series([100.0, 105.0, 110.0])
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_single_value_zero(self):
        equity = pd.Series([100.0])
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_empty_zero(self):
        equity = pd.Series([], dtype=float)
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_zero_equity_no_nan(self):
        """All-zero equity must not propagate NaN (risk/metrics.py:55->56)."""
        result = calculate_max_drawdown(pd.Series([0.0, 0.0, 0.0]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_zero_then_positive_no_nan(self):
        """Equity starting at zero then rising must not propagate NaN."""
        result = calculate_max_drawdown(pd.Series([0.0, 0.0, 5.0, 10.0]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)


class TestCalculateSharpeRatio:
    """Tests for calculate_sharpe_ratio."""

    def test_annualized_with_risk_free(self):
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02)
        expected = (RETURNS.mean() - 0.02 / 252) / RETURNS.std() * np.sqrt(252)
        assert sharpe == pytest.approx(expected)

    def test_non_annualized(self):
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, annualize=False)
        annual = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, annualize=True)
        assert sharpe == pytest.approx(annual / np.sqrt(252))

    def test_empty_returns_zero(self):
        assert calculate_sharpe_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_zero_volatility_zero(self):
        flat = pd.Series([0.01, 0.01, 0.01])
        assert calculate_sharpe_ratio(flat) == pytest.approx(0.0)


class TestCalculateSortinoRatio:
    """Tests for calculate_sortino_ratio."""

    def test_normal_case(self):
        sortino = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02)
        downside = RETURNS[RETURNS < 0]
        expected = (RETURNS.mean() - 0.02 / 252) / downside.std() * np.sqrt(252)
        assert sortino == pytest.approx(expected)

    def test_no_downside_returns_zero(self):
        positive = pd.Series([0.01, 0.02, 0.03])
        assert calculate_sortino_ratio(positive) == pytest.approx(0.0)

    def test_empty_returns_zero(self):
        assert calculate_sortino_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_single_downside_returns_zero(self):
        """A single downside observation must not yield NaN (downside std undefined)."""
        single_down = pd.Series([0.01, 0.02, -0.01, 0.02, 0.01])
        result = calculate_sortino_ratio(single_down, risk_free_rate=0.02)
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_identical_downside_returns_zero(self):
        identical = pd.Series([0.01, -0.02, -0.02, 0.01])
        assert calculate_sortino_ratio(identical) == pytest.approx(0.0)

    def test_non_annualized(self):
        """annualize=False skips the sqrt(252) scaling (risk/metrics.py:90->92)."""
        non_annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=False)
        annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=True)
        assert non_annual == pytest.approx(annual / np.sqrt(252))


class TestCalculateVar:
    """Tests for calculate_var."""

    def test_var_95(self):
        result = calculate_var(RETURNS, confidence=0.95)
        assert result == pytest.approx(np.percentile(RETURNS, 5))

    def test_var_99(self):
        result = calculate_var(RETURNS, confidence=0.99)
        assert result == pytest.approx(np.percentile(RETURNS, 1))

    def test_empty_returns_zero(self):
        assert calculate_var(pd.Series([], dtype=float)) == pytest.approx(0.0)


class TestCalculateBeta:
    """Tests for calculate_beta."""

    def test_beta_correlation(self):
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        aligned = pd.concat([RETURNS, MARKET_RETURNS], axis=1).dropna()
        expected = aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / aligned.iloc[:, 1].var()
        assert beta == pytest.approx(expected)

    def test_beta_identical_series_is_one(self):
        beta = calculate_beta(RETURNS, RETURNS)
        assert beta == pytest.approx(1.0)

    def test_beta_insufficient_samples(self):
        small = pd.Series([0.01])
        assert calculate_beta(small, MARKET_RETURNS) == pytest.approx(0.0)

    def test_beta_zero_market_variance(self):
        constant = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        assert calculate_beta(RETURNS, constant) == pytest.approx(0.0)

    def test_beta_non_overlapping_indices(self):
        """Aligned overlap fewer than 2 points yields 0.0 beta."""
        idx1 = pd.date_range("2020-01-01", periods=5)
        idx2 = pd.date_range("2021-01-01", periods=5)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=idx1)
        market = pd.Series([-0.01, 0.0, 0.02, 0.03, 0.04], index=idx2)
        assert calculate_beta(returns, market) == pytest.approx(0.0)


class TestCalculateAlpha:
    """Tests for calculate_alpha."""

    def test_alpha_value(self):
        alpha = calculate_alpha(RETURNS, MARKET_RETURNS, risk_free_rate=0.02)
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        expected = RETURNS.mean() * 252 - (0.02 + beta * (MARKET_RETURNS.mean() * 252 - 0.02))
        assert alpha == pytest.approx(expected)

    def test_alpha_zero_beta(self):
        constant = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        assert calculate_alpha(RETURNS, constant) == pytest.approx(0.0)


class TestCalculateCalmarRatio:
    """Tests for calculate_calmar_ratio."""

    def test_calmar_value(self):
        equity = pd.Series([100.0, 110.0, 90.0, 95.0])
        calmar = calculate_calmar_ratio(RETURNS, equity)
        expected = (RETURNS.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calmar == pytest.approx(expected)

    def test_calmar_no_drawdown_zero(self):
        equity = pd.Series([100.0, 105.0, 110.0])
        assert calculate_calmar_ratio(RETURNS, equity) == pytest.approx(0.0)

    def test_calmar_empty_returns_zero(self):
        equity = pd.Series([100.0])
        assert calculate_calmar_ratio(pd.Series([], dtype=float), equity) == pytest.approx(0.0)


class TestRiskMetricsDataclass:
    """Tests for RiskMetrics container."""

    def test_to_dict_keys(self):
        metrics = RiskMetrics(
            sharpe_ratio=1.5,
            sortino_ratio=0.8,
            max_drawdown=-0.1,
            volatility=0.2,
            var_95=-0.05,
            var_99=-0.08,
            beta=1.1,
            alpha=0.02,
            calmar_ratio=2.3,
        )
        data = metrics.to_dict()
        assert set(data.keys()) == {
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "volatility",
            "var_95",
            "var_99",
            "beta",
            "alpha",
            "calmar_ratio",
        }
        assert data["sharpe_ratio"] == pytest.approx(1.5)
        assert data["calmar_ratio"] == pytest.approx(2.3)

    def test_defaults(self):
        metrics = RiskMetrics()
        data = metrics.to_dict()
        assert all(v == 0.0 for v in data.values())


class TestCalculateAllMetrics:
    """Tests for calculate_all_metrics orchestration."""

    def test_without_market_returns(self):
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0])
        metrics = calculate_all_metrics(equity, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(0.0)
        assert metrics.alpha == pytest.approx(0.0)
        assert isinstance(metrics.sharpe_ratio, float)
        assert isinstance(metrics.volatility, float)
        assert isinstance(metrics.var_95, float)
        result = metrics.to_dict()
        assert set(result.keys()) == RiskMetrics().to_dict().keys()

    def test_with_market_returns_beta_one(self):
        idx = pd.date_range("2020-01-01", periods=6)
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0, 118.0], index=idx)
        market = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, market_returns=market, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(1.0)
        assert metrics.alpha == pytest.approx(0.0, abs=1e-9)

    def test_with_market_returns_custom_beta(self):
        equity = pd.Series([100.0, 95.0, 93.1, 94.031, 96.85, 104.61])
        market = pd.Series([100.0, 96.0, 95.0, 97.0, 98.0, 101.0])
        metrics = calculate_all_metrics(
            equity, market_returns=calculate_returns(market), risk_free_rate=0.02
        )
        expected_beta = calculate_beta(calculate_returns(equity), calculate_returns(market))
        assert metrics.beta == pytest.approx(expected_beta)
        expected_alpha = calculate_alpha(
            calculate_returns(equity), calculate_returns(market), risk_free_rate=0.02
        )
        assert metrics.alpha == pytest.approx(expected_alpha)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
