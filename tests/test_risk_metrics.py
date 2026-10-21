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

    def test_returns_with_nan_dropped(self):
        prices = pd.Series([1.0, float("nan"), 2.0, 3.0])
        res = calculate_returns(prices)
        assert res.isna().sum() == 0

    def test_returns_all_same(self):
        prices = pd.Series([1.0, 1.0, 1.0])
        res = calculate_returns(prices)
        assert all(v == 0.0 for v in res)

    def test_returns_two_points(self):
        prices = pd.Series([1.0, 2.0])
        res = calculate_returns(prices)
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(1.0)
        prices = pd.Series([100.0, 90.0, 99.0])
        result = calculate_returns(prices)
        assert len(result) == 2

    def test_returns_zero_previous_price_no_inf(self):
        """A zero previous price must not produce inf/NaN returns.

        The move out of a zero price is undefined and dropped, so downstream
        metrics stay finite instead of NaN/inf (quant_trading/risk/metrics.py:calculate_returns).
        """
        prices = pd.Series([1.0, 0.0, 2.0])
        res = calculate_returns(prices)
        assert np.isfinite(res).all()
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(-1.0)


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

    def test_periods_per_year_scales_annualization(self):
        """Annualized volatility must scale with the requested periods per year."""
        raw = calculate_volatility(RETURNS, annualize=False)
        weekly = calculate_volatility(RETURNS, annualize=True, periods_per_year=52)
        assert weekly == pytest.approx(raw * np.sqrt(52))
        assert weekly != pytest.approx(raw * np.sqrt(252))

    def test_periods_per_year_ignored_when_not_annualizing(self):
        """The raw (non-annualized) volatility is independent of periods_per_year."""
        raw = calculate_volatility(RETURNS, annualize=False)
        assert calculate_volatility(RETURNS, annualize=False, periods_per_year=52) == pytest.approx(
            raw
        )


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

    def test_single_observation_no_nan(self):
        """A single return has undefined std; must not propagate NaN."""
        result = calculate_sharpe_ratio(pd.Series([0.01]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_periods_per_year_used_for_risk_free_and_scaling(self):
        """The annual risk-free rate and the sqrt scaling must use periods_per_year."""
        expected = (RETURNS.mean() - 0.02 / 52) / RETURNS.std() * np.sqrt(52)
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, periods_per_year=52)
        assert sharpe == pytest.approx(expected)

    def test_periods_per_year_differs_from_default(self):
        """A non-daily annualization period must change the Sharpe ratio."""
        daily = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02)
        monthly = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, periods_per_year=12)
        assert monthly != pytest.approx(daily)


class TestCalculateSortinoRatio:
    """Tests for calculate_sortino_ratio."""

    @staticmethod
    def _downside_deviation(returns: pd.Series, mar: float) -> float:
        """The documented downside deviation: sqrt(sum(min(0, r - MAR)^2) / N)."""
        shortfalls = np.minimum(returns.to_numpy(dtype=float) - mar, 0.0)
        return float(np.sqrt(np.mean(shortfalls**2)))

    def test_normal_case(self):
        sortino = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02)
        mar = 0.02 / 252
        downside_dev = self._downside_deviation(RETURNS, mar)
        expected = (RETURNS.mean() - mar) / downside_dev * np.sqrt(252)
        assert sortino == pytest.approx(expected)

    def test_no_downside_returns_zero(self):
        positive = pd.Series([0.01, 0.02, 0.03])
        assert calculate_sortino_ratio(positive) == pytest.approx(0.0)

    def test_empty_returns_zero(self):
        assert calculate_sortino_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_single_downside_is_defined(self):
        """A single losing period still yields a defined downside deviation.

        The downside deviation is taken over the full sample, so one losing
        observation contributes its squared shortfall instead of making the
        metric undefined.
        """
        single_down = pd.Series([0.01, 0.02, -0.01, 0.02, 0.01])
        result = calculate_sortino_ratio(single_down, risk_free_rate=0.02)
        assert not np.isnan(result)
        mar = 0.02 / 252
        expected = (
            (single_down.mean() - mar) / self._downside_deviation(single_down, mar) * np.sqrt(252)
        )
        assert result == pytest.approx(expected)
        assert result > 0.0

    def test_loss_only_series_is_negative(self):
        """A strategy that never beats the MAR must not report a zero ratio."""
        losing = pd.Series([-0.01, -0.02, -0.01, -0.03])
        result = calculate_sortino_ratio(losing, risk_free_rate=0.02)
        assert not np.isnan(result)
        assert result < 0.0

    def test_identical_downside_is_not_zero(self):
        """Identical losing periods still have a non-zero downside deviation."""
        identical = pd.Series([0.01, -0.02, -0.02, 0.01])
        result = calculate_sortino_ratio(identical, risk_free_rate=0.02)
        assert not np.isnan(result)
        mar = 0.02 / 252
        expected = (
            (identical.mean() - mar) / self._downside_deviation(identical, mar) * np.sqrt(252)
        )
        assert result == pytest.approx(expected)
        assert result < 0.0

    def test_non_annualized(self):
        """annualize=False skips the sqrt(252) scaling (risk/metrics.py:90->92)."""
        non_annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=False)
        annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=True)
        assert non_annual == pytest.approx(annual / np.sqrt(252))

    def test_periods_per_year_used_for_risk_free_and_scaling(self):
        """The annual risk-free rate and the sqrt scaling must use periods_per_year."""
        mar = 0.02 / 52
        downside_dev = self._downside_deviation(RETURNS, mar)
        expected = (RETURNS.mean() - mar) / downside_dev * np.sqrt(52)
        sortino = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, periods_per_year=52)
        assert sortino == pytest.approx(expected)


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

    def test_beta_non_overlapping_indices_aligns_positionally(self):
        """When index alignment leaves no overlap, series fall back to positional alignment.

        Two same-length series with disjoint date indices can no longer be
        matched by label, so they are paired by position instead of silently
        returning 0.0 beta.
        """
        idx1 = pd.date_range("2020-01-01", periods=5)
        idx2 = pd.date_range("2021-01-01", periods=5)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=idx1)
        market = pd.Series([-0.01, 0.0, 0.02, 0.03, 0.04], index=idx2)
        # Positional alignment pairs the two same-length series by position.
        expected = calculate_beta(returns.reset_index(drop=True), market.reset_index(drop=True))
        assert calculate_beta(returns, market) == pytest.approx(expected)

    def test_beta_insufficient_aligned_points_after_fallback(self):
        """Both series have >= 2 points but NaNs leave < 2 aligned -> 0.0 beta.

        Index alignment and the positional fallback both drop the NaN rows,
        leaving too few observations, so beta is 0.0
        (quant_trading/risk/metrics.py:calculate_beta).
        """
        returns = pd.Series([0.01, float("nan")])
        market = pd.Series([0.01, 0.02])
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

    def test_alpha_periods_per_year_scales_annualization(self):
        """Alpha annualization must follow the requested periods per year."""
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        expected = RETURNS.mean() * 12 - (0.02 + beta * (MARKET_RETURNS.mean() * 12 - 0.02))
        alpha = calculate_alpha(RETURNS, MARKET_RETURNS, risk_free_rate=0.02, periods_per_year=12)
        assert alpha == pytest.approx(expected)


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

    def test_calmar_periods_per_year_scales_annual_return(self):
        """The annualized return in the Calmar ratio must follow periods_per_year."""
        equity = pd.Series([100.0, 110.0, 90.0, 95.0])
        expected = (RETURNS.mean() * 12) / abs(calculate_max_drawdown(equity))
        calmar = calculate_calmar_ratio(RETURNS, equity, periods_per_year=12)
        assert calmar == pytest.approx(expected)


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

    def test_periods_per_year_threaded_to_every_metric(self):
        """calculate_all_metrics must use the requested periods per year everywhere."""
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0, 112.0, 120.0])
        returns = calculate_returns(equity)
        market = pd.Series([100.0, 102.0, 104.0, 103.0, 107.0, 109.0, 111.0])
        metrics = calculate_all_metrics(
            equity,
            market_returns=calculate_returns(market),
            risk_free_rate=0.02,
            periods_per_year=52,
        )
        assert metrics.volatility == pytest.approx(
            calculate_volatility(returns, periods_per_year=52)
        )
        assert metrics.sharpe_ratio == pytest.approx(
            calculate_sharpe_ratio(returns, risk_free_rate=0.02, periods_per_year=52)
        )
        assert metrics.sortino_ratio == pytest.approx(
            calculate_sortino_ratio(returns, risk_free_rate=0.02, periods_per_year=52)
        )
        assert metrics.calmar_ratio == pytest.approx(
            calculate_calmar_ratio(returns, equity, periods_per_year=52)
        )
        assert metrics.alpha == pytest.approx(
            calculate_alpha(
                returns, calculate_returns(market), risk_free_rate=0.02, periods_per_year=52
            )
        )

    def test_default_periods_per_year_matches_daily_annualization(self):
        """The default (252) must reproduce the documented daily annualization."""
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0, 112.0, 120.0])
        returns = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, risk_free_rate=0.02)
        assert metrics.volatility == pytest.approx(returns.std() * np.sqrt(252))
        assert metrics.sharpe_ratio == pytest.approx(
            calculate_sharpe_ratio(returns, risk_free_rate=0.02, periods_per_year=252)
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

    def test_var_single_value(self):
        """Single value returns: percentile behavior should not produce NaN."""
        result = calculate_var(pd.Series([0.01]), confidence=0.95)
        assert not np.isnan(result)
        assert result == pytest.approx(0.01)

    def test_var_single_value_high_confidence(self):
        """Single value with high confidence."""
        result = calculate_var(pd.Series([-0.05]), confidence=0.99)
        assert not np.isnan(result)
        assert result == pytest.approx(-0.05)

    def test_beta_market_single_value(self):
        """Market with single value paired with returns < 2 aligned should give 0."""
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.01])  # only 1 value
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_both_single_values(self):
        returns = pd.Series([0.01])
        market = pd.Series([0.02])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_market_constant_after_alignment(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.05, 0.05, 0.05])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_alpha_insufficient_returns(self):
        small = pd.Series([0.01])
        market = pd.Series([0.01, 0.02, 0.03])
        assert calculate_alpha(small, market) == pytest.approx(0.0)

    def test_alpha_insufficient_market(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        small = pd.Series([0.01])
        assert calculate_alpha(returns, small) == pytest.approx(0.0)

    def test_returns_with_nan_dropped(self):
        prices = pd.Series([1.0, float("nan"), 2.0, 3.0])
        res = calculate_returns(prices)
        assert res.isna().sum() == 0

    def test_returns_all_same_extra(self):
        prices = pd.Series([1.0, 1.0, 1.0])
        res = calculate_returns(prices)
        assert all(v == 0.0 for v in res)

    def test_returns_two_points_extra(self):
        prices = pd.Series([1.0, 2.0])
        res = calculate_returns(prices)
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(1.0)


class TestNanHandling:
    """Tests for NaN handling in risk metrics."""

    def test_var_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_var(r)
        assert not np.isnan(res)
        assert res < 0

    def test_volatility_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_volatility(r)
        assert not np.isnan(res)
        assert res > 0

    def test_sharpe_ratio_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, 0.03])
        res = calculate_sharpe_ratio(r)
        assert not np.isnan(res)

    def test_sortino_ratio_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, -0.02])
        res = calculate_sortino_ratio(r)
        assert not np.isnan(res)

    def test_max_drawdown_with_nans(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 100.0])
        res = calculate_max_drawdown(eq)
        assert not np.isnan(res)

    def test_beta_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_beta(r, m)
        assert not np.isnan(res)

    def test_alpha_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_alpha(r, m)
        assert not np.isnan(res)

    def test_calmar_ratio_with_nans(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 90.0])
        r = calculate_returns(eq)
        res = calculate_calmar_ratio(r, eq)
        assert not np.isnan(res)

    def test_all_metrics_with_nans_in_equity(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 100.0, 95.0])
        m = pd.Series([0.01, float("nan"), 0.02, 0.01, 0.0, -0.01])
        res = calculate_all_metrics(eq, market_returns=m)
        assert not np.isnan(res.sharpe_ratio)
        assert not np.isnan(res.volatility)
        assert not np.isnan(res.var_95)


class TestAlphaAlignment:
    """Tests for calculate_alpha alignment consistency with calculate_beta.

    Beta is computed from the overlapping-index sample, so alpha must use the
    same observations; otherwise the two are mutually inconsistent when the
    input series have non-overlapping indices or NaN values.
    """

    def test_alpha_uses_aligned_sample_with_misaligned_indices(self):
        """Alpha must average the same aligned observations used for beta."""
        returns = pd.Series([0.01, 0.02, 0.03], index=[0, 1, 2])
        market = pd.Series([0.01, 0.02, 0.03], index=[1, 2, 3])

        beta = calculate_beta(returns, market)
        aligned = pd.concat([returns, market], axis=1).dropna()
        expected = aligned.iloc[:, 0].mean() * 252 - (
            0.02 + beta * (aligned.iloc[:, 1].mean() * 252 - 0.02)
        )

        assert calculate_alpha(returns, market) == pytest.approx(expected)

    def test_alpha_non_overlapping_indices_returns_zero(self):
        """Completely disjoint indices yield no aligned sample -> alpha 0."""
        returns = pd.Series([0.01, 0.02, 0.03], index=[0, 1, 2])
        market = pd.Series([0.01, 0.02, 0.03], index=[3, 4, 5])
        assert calculate_alpha(returns, market) == pytest.approx(0.0)

    def test_alpha_partial_overlap_uses_only_aligned_points(self):
        """Only overlapping dates contribute to the alpha means."""
        idx = pd.date_range("2020-01-01", periods=5)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=idx)
        market = pd.Series([0.00, 0.01, 0.02, 0.03, 0.04], index=idx[[1, 2, 3, 4, 0]])

        beta = calculate_beta(returns, market)
        aligned = pd.concat([returns, market], axis=1).dropna()
        expected = aligned.iloc[:, 0].mean() * 252 - (
            0.02 + beta * (aligned.iloc[:, 1].mean() * 252 - 0.02)
        )
        assert calculate_alpha(returns, market) == pytest.approx(expected)

    def test_alpha_consistent_with_beta_in_calculate_all_metrics(self):
        """calculate_all_metrics must report alpha consistent with its beta."""
        idx = pd.date_range("2020-01-01", periods=6)
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0, 118.0], index=idx)
        market = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, market_returns=market, risk_free_rate=0.02)

        expected_alpha = calculate_alpha(calculate_returns(equity), market, risk_free_rate=0.02)
        assert metrics.alpha == pytest.approx(expected_alpha)
        assert metrics.beta == pytest.approx(calculate_beta(calculate_returns(equity), market))

    def test_alpha_nan_in_market_dropped_before_alignment(self):
        """NaN values in either series are dropped by the shared alignment."""
        returns = pd.Series([0.01, float("nan"), 0.02, -0.01])
        market = pd.Series([0.005, 0.01, float("nan"), -0.005])
        result = calculate_alpha(returns, market)
        assert not np.isnan(result)

        aligned = pd.concat([returns, market], axis=1).dropna()
        beta = calculate_beta(returns, market)
        expected = aligned.iloc[:, 0].mean() * 252 - (
            0.02 + beta * (aligned.iloc[:, 1].mean() * 252 - 0.02)
        )
        assert result == pytest.approx(expected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

    def test_var_single_value(self):
        """Single value returns: percentile behavior should not produce NaN."""
        result = calculate_var(pd.Series([0.01]), confidence=0.95)
        assert not np.isnan(result)
        assert result == pytest.approx(0.01)

    def test_var_single_value_high_confidence(self):
        """Single value with high confidence."""
        result = calculate_var(pd.Series([-0.05]), confidence=0.99)
        assert not np.isnan(result)
        assert result == pytest.approx(-0.05)

    def test_beta_market_single_value(self):
        """Market with single value paired with returns < 2 aligned should give 0."""
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.01])  # only 1 value
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_both_single_values(self):
        returns = pd.Series([0.01])
        market = pd.Series([0.02])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_market_constant_after_alignment(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.05, 0.05, 0.05])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_alpha_insufficient_returns(self):
        small = pd.Series([0.01])
        market = pd.Series([0.01, 0.02, 0.03])
        assert calculate_alpha(small, market) == pytest.approx(0.0)

    def test_alpha_insufficient_market(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        small = pd.Series([0.01])
        assert calculate_alpha(returns, small) == pytest.approx(0.0)

    def test_returns_with_nan_dropped(self):
        prices = pd.Series([1.0, float("nan"), 2.0, 3.0])
        res = calculate_returns(prices)
        assert res.isna().sum() == 0

    def test_returns_all_same_extra(self):
        prices = pd.Series([1.0, 1.0, 1.0])
        res = calculate_returns(prices)
        assert all(v == 0.0 for v in res)

    def test_returns_two_points_extra(self):
        prices = pd.Series([1.0, 2.0])
        res = calculate_returns(prices)
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(1.0)

    def test_var_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_var(r)
        assert not np.isnan(res)
        assert res < 0

    def test_volatility_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_volatility(r)
        assert not np.isnan(res)
        assert res > 0

    def test_sharpe_ratio_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, 0.03])
        res = calculate_sharpe_ratio(r)
        assert not np.isnan(res)

    def test_sortino_ratio_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, -0.02])
        res = calculate_sortino_ratio(r)
        assert not np.isnan(res)

    def test_max_drawdown_with_nans(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 100.0])
        res = calculate_max_drawdown(eq)
        assert not np.isnan(res)

    def test_beta_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_beta(r, m)
        assert not np.isnan(res)

    def test_alpha_with_nans(self):
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_alpha(r, m)
        assert not np.isnan(res)

    def test_calmar_ratio_with_nans(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 90.0])
        r = calculate_returns(eq)
        res = calculate_calmar_ratio(r, eq)
        assert not np.isnan(res)

    def test_all_metrics_with_nans_in_equity(self):
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 100.0, 95.0])
        m = pd.Series([0.01, float("nan"), 0.02, 0.01, 0.0, -0.01])
        res = calculate_all_metrics(eq, market_returns=m)
        assert not np.isnan(res.sharpe_ratio)
        assert not np.isnan(res.volatility)
        assert not np.isnan(res.var_95)
