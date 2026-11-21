"""Tests for risk metrics calculation utilities."""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from quant_trading.risk.metrics import (
    RiskMetrics,
    _align_series,
    calculate_all_metrics,
    calculate_alpha,
    calculate_beta,
    calculate_calmar_ratio,
    calculate_cvar,
    calculate_information_ratio,
    calculate_max_drawdown,
    calculate_omega_ratio,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_treynor_ratio,
    calculate_ulcer_index,
    calculate_var,
    calculate_volatility,
)

RETURNS = pd.Series([-0.05, -0.02, 0.01, 0.03, 0.08])
MARKET_RETURNS = pd.Series([-0.04, -0.01, 0.02, 0.04, 0.09])
EQUITY_STEADY = pd.Series([100.0, 105.0, 110.0])


class TestCalculateReturns:
    """Tests for calculate_returns."""

    def test_basic_returns(self) -> None:
        prices = pd.Series([100.0, 110.0, 121.0])
        expected = pd.Series([0.1, 0.1])
        result = calculate_returns(prices)
        np.testing.assert_allclose(result.to_numpy(), expected.to_numpy())

    def test_single_price_returns_empty(self) -> None:
        prices = pd.Series([100.0])
        result = calculate_returns(prices)
        assert len(result) == 0

    def test_empty_prices_returns_empty(self) -> None:
        prices = pd.Series([], dtype=float)
        result = calculate_returns(prices)
        assert len(result) == 0

    def test_no_negative_indexing_leak(self) -> None:
        prices = pd.Series([100.0, 90.0, 99.0])
        result = calculate_returns(prices)
        assert len(result) == 2

    def test_returns_with_nan_dropped(self) -> None:
        prices = pd.Series([1.0, float("nan"), 2.0, 3.0])
        res = calculate_returns(prices)
        assert res.isna().sum() == 0

    def test_returns_all_same(self) -> None:
        prices = pd.Series([1.0, 1.0, 1.0])
        res = calculate_returns(prices)
        assert all(v == 0.0 for v in res)

    def test_returns_two_points(self) -> None:
        prices = pd.Series([1.0, 2.0])
        res = calculate_returns(prices)
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(1.0)
        prices = pd.Series([100.0, 90.0, 99.0])
        result = calculate_returns(prices)
        assert len(result) == 2

    def test_returns_zero_previous_price_no_inf(self) -> None:
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

    def test_raw_volatility(self) -> None:
        vol = calculate_volatility(RETURNS, annualize=False)
        assert vol == pytest.approx(RETURNS.std())

    def test_annualized_volatility(self) -> None:
        vol = calculate_volatility(RETURNS, annualize=True)
        assert vol == pytest.approx(RETURNS.std() * np.sqrt(252))

    def test_annualized_scales_raw(self) -> None:
        raw = calculate_volatility(RETURNS, annualize=False)
        annual = calculate_volatility(RETURNS, annualize=True)
        assert annual == pytest.approx(raw * np.sqrt(252))

    def test_empty_series_returns_zero(self) -> None:
        """Empty returns must not propagate NaN (risk/metrics.py:44->47)."""
        result = calculate_volatility(pd.Series([], dtype=float))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_empty_series_non_annualized_returns_zero(self) -> None:
        """Empty returns must not propagate NaN when annualize=False."""
        result = calculate_volatility(pd.Series([], dtype=float), annualize=False)
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_single_value_zero(self) -> None:
        """A single return has undefined std; must not propagate NaN."""
        result = calculate_volatility(pd.Series([0.01]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_periods_per_year_scales_annualization(self) -> None:
        """Annualized volatility must scale with the requested periods per year."""
        raw = calculate_volatility(RETURNS, annualize=False)
        weekly = calculate_volatility(RETURNS, annualize=True, periods_per_year=52)
        assert weekly == pytest.approx(raw * np.sqrt(52))
        assert weekly != pytest.approx(raw * np.sqrt(252))

    def test_periods_per_year_ignored_when_not_annualizing(self) -> None:
        """The raw (non-annualized) volatility is independent of periods_per_year."""
        raw = calculate_volatility(RETURNS, annualize=False)
        assert calculate_volatility(RETURNS, annualize=False, periods_per_year=52) == pytest.approx(
            raw
        )


class TestCalculateMaxDrawdown:
    """Tests for calculate_max_drawdown."""

    def test_drawdown_from_peak(self) -> None:
        equity = pd.Series([100.0, 110.0, 90.0, 95.0])
        result = calculate_max_drawdown(equity)
        assert result == pytest.approx((90.0 - 110.0) / 110.0)

    def test_no_drawdown_monotonic(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0])
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_single_value_zero(self) -> None:
        equity = pd.Series([100.0])
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_empty_zero(self) -> None:
        equity = pd.Series([], dtype=float)
        assert calculate_max_drawdown(equity) == pytest.approx(0.0)

    def test_zero_equity_no_nan(self) -> None:
        """All-zero equity must not propagate NaN (risk/metrics.py:55->56)."""
        result = calculate_max_drawdown(pd.Series([0.0, 0.0, 0.0]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_zero_then_positive_no_nan(self) -> None:
        """Equity starting at zero then rising must not propagate NaN."""
        result = calculate_max_drawdown(pd.Series([0.0, 0.0, 5.0, 10.0]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_negative_equity_against_zero_peak_is_finite(self) -> None:
        """A negative value while the running peak is zero must not return -inf."""
        result = calculate_max_drawdown(pd.Series([0.0, -5.0, 10.0]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)

    def test_zero_peak_is_ignored_before_later_drawdown(self) -> None:
        """Undefined zero-peak points are skipped; later drawdowns still count."""
        result = calculate_max_drawdown(pd.Series([0.0, -5.0, 10.0, 5.0]))
        assert np.isfinite(result)
        assert result == pytest.approx(-0.5)

    def test_all_negative_equity_reports_neutral_drawdown(self) -> None:
        """An all-negative equity curve has no positive running peak, so the
        drawdown ratio is undefined everywhere and reports neutral (0.0),
        matching the chart-level drawdown series."""
        result = calculate_max_drawdown(pd.Series([-5.0, -10.0, -3.0]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)

    def test_zero_and_negative_equity_reports_neutral_drawdown(self) -> None:
        """An equity curve that is zero or negative throughout reports a
        neutral drawdown because no running peak is strictly positive."""
        result = calculate_max_drawdown(pd.Series([0.0, -5.0, -2.0]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)

    def test_all_infinite_equity_reports_neutral_drawdown(self) -> None:
        """An equity curve whose values are all infinite has no finite
        running peak, so every drawdown ratio is non-finite and the
        empty-drawdown fallback (metrics.py:217) reports neutral."""
        result = calculate_max_drawdown(pd.Series([np.inf, np.inf, np.inf]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)

    def test_zero_then_infinite_reports_neutral_drawdown(self) -> None:
        """Zero running peak makes the ratio undefined; a later infinite
        value is dropped, leaving an empty drawdown series that hits the
        metrics.py:217 fallback."""
        result = calculate_max_drawdown(pd.Series([0.0, np.inf]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)


class TestCalculateUlcerIndex:
    """Tests for calculate_ulcer_index."""

    def test_ulcer_matches_manual_rms_of_drawdowns(self) -> None:
        equity = pd.Series([100.0, 110.0, 105.0, 90.0, 95.0])
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        expected = float(np.sqrt(np.mean(drawdown**2)))
        assert calculate_ulcer_index(equity) == pytest.approx(expected)

    def test_ulcer_known_value(self) -> None:
        equity = pd.Series([100.0, 110.0, 105.0, 90.0, 95.0])
        assert calculate_ulcer_index(equity) == pytest.approx(0.10365231137264891)

    def test_monotonic_increasing_is_zero(self) -> None:
        equity = pd.Series([100.0, 101.0, 102.0, 103.0])
        assert calculate_ulcer_index(equity) == pytest.approx(0.0)

    def test_deeper_drawdown_scores_higher(self) -> None:
        shallow = pd.Series([100.0, 110.0, 105.0, 110.0])
        deep = pd.Series([100.0, 110.0, 80.0, 110.0])
        assert calculate_ulcer_index(deep) > calculate_ulcer_index(shallow)

    def test_duration_increases_index(self) -> None:
        """A drawdown held longer scores higher than a brief one of equal depth."""
        brief = pd.Series([100.0, 110.0, 99.0, 110.0])
        prolonged = pd.Series([100.0, 110.0, 99.0, 99.0, 110.0])
        assert calculate_ulcer_index(prolonged) > calculate_ulcer_index(brief)

    def test_empty_zero(self) -> None:
        assert calculate_ulcer_index(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_single_value_zero(self) -> None:
        assert calculate_ulcer_index(pd.Series([100.0])) == pytest.approx(0.0)

    def test_nan_dropped(self) -> None:
        equity = pd.Series([100.0, float("nan"), 90.0, 95.0])
        result = calculate_ulcer_index(equity)
        assert not np.isnan(result)
        # The NaN row is dropped, so the result matches the curve without it.
        expected = calculate_ulcer_index(pd.Series([100.0, 90.0, 95.0]))
        assert result == pytest.approx(expected)

    def test_all_zero_equity_no_nan(self) -> None:
        result = calculate_ulcer_index(pd.Series([0.0, 0.0, 0.0]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_zero_then_positive_no_nan(self) -> None:
        result = calculate_ulcer_index(pd.Series([0.0, 0.0, 5.0, 10.0]))
        assert not np.isnan(result)

    def test_non_negative(self) -> None:
        equity = pd.Series([100.0, 90.0, 120.0, 60.0, 130.0])
        assert calculate_ulcer_index(equity) >= 0.0

    def test_all_negative_equity_reports_neutral_ulcer_index(self) -> None:
        result = calculate_ulcer_index(pd.Series([-5.0, -10.0, -3.0]))
        assert result == pytest.approx(0.0)

    def test_zero_and_negative_equity_reports_neutral_ulcer_index(self) -> None:
        result = calculate_ulcer_index(pd.Series([0.0, -5.0, -2.0]))
        assert result == pytest.approx(0.0)

    def test_overflow_drawdown_reports_neutral_ulcer_index(self) -> None:
        """An equity curve that collapses by ~1e155 produces a non-finite
        ulcer (metrics.py:1107) and must report neutral rather than NaN."""
        result = calculate_ulcer_index(pd.Series([1.0, 1.0 - 1e155]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)

    def test_extreme_negative_drawdown_reports_neutral_ulcer_index(self) -> None:
        """A drop to -1e200 from a tiny peak overflows the squared drawdown,
        triggering the non-finite ulcer guard at metrics.py:1107."""
        result = calculate_ulcer_index(pd.Series([1.0, -1e200]))
        assert np.isfinite(result)
        assert result == pytest.approx(0.0)


class TestCalculateSharpeRatio:
    """Tests for calculate_sharpe_ratio."""

    def test_annualized_with_risk_free(self) -> None:
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02)
        expected = (RETURNS.mean() - 0.02 / 252) / RETURNS.std() * np.sqrt(252)
        assert sharpe == pytest.approx(expected)

    def test_non_annualized(self) -> None:
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, annualize=False)
        annual = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, annualize=True)
        assert sharpe == pytest.approx(annual / np.sqrt(252))

    def test_empty_returns_zero(self) -> None:
        assert calculate_sharpe_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_zero_volatility_zero(self) -> None:
        flat = pd.Series([0.01, 0.01, 0.01])
        assert calculate_sharpe_ratio(flat) == pytest.approx(0.0)

    def test_single_observation_no_nan(self) -> None:
        """A single return has undefined std; must not propagate NaN."""
        result = calculate_sharpe_ratio(pd.Series([0.01]))
        assert not np.isnan(result)
        assert result == pytest.approx(0.0)

    def test_periods_per_year_used_for_risk_free_and_scaling(self) -> None:
        """The annual risk-free rate and the sqrt scaling must use periods_per_year."""
        expected = (RETURNS.mean() - 0.02 / 52) / RETURNS.std() * np.sqrt(52)
        sharpe = calculate_sharpe_ratio(RETURNS, risk_free_rate=0.02, periods_per_year=52)
        assert sharpe == pytest.approx(expected)

    def test_periods_per_year_differs_from_default(self) -> None:
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

    def test_normal_case(self) -> None:
        sortino = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02)
        mar = 0.02 / 252
        downside_dev = self._downside_deviation(RETURNS, mar)
        expected = (RETURNS.mean() - mar) / downside_dev * np.sqrt(252)
        assert sortino == pytest.approx(expected)

    def test_no_downside_returns_zero(self) -> None:
        positive = pd.Series([0.01, 0.02, 0.03])
        assert calculate_sortino_ratio(positive) == pytest.approx(0.0)

    def test_empty_returns_zero(self) -> None:
        assert calculate_sortino_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_single_downside_is_defined(self) -> None:
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

    def test_loss_only_series_is_negative(self) -> None:
        """A strategy that never beats the MAR must not report a zero ratio."""
        losing = pd.Series([-0.01, -0.02, -0.01, -0.03])
        result = calculate_sortino_ratio(losing, risk_free_rate=0.02)
        assert not np.isnan(result)
        assert result < 0.0

    def test_identical_downside_is_not_zero(self) -> None:
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

    def test_constant_returns_zero_not_degenerate(self) -> None:
        """A constant return series must not produce a degenerate +/-1 ratio.

        A flat portfolio (zero trades, zero variance) has no downside to
        measure, yet every observation falls on one side of the MAR, so the
        downside deviation is non-zero and the raw ratio collapses to
        +/-1 times the annualization factor (-15.87 for daily data). This is
        the same zero-variance guard calculate_sharpe_ratio already applies,
        so the Sortino must report 0.0 for a flat portfolio rather than a
        meaningless negative number.
        """
        flat = pd.Series([0.0] * 10)
        assert flat.std() == 0.0
        assert calculate_sortino_ratio(flat) == pytest.approx(0.0)
        assert not np.isnan(calculate_sortino_ratio(flat))

    def test_constant_negative_returns_zero(self) -> None:
        """A constant losing series (zero variance) must also report 0.0."""
        constant_loss = pd.Series([-0.01] * 5)
        assert constant_loss.std() == 0.0
        assert calculate_sortino_ratio(constant_loss) == pytest.approx(0.0)

    def test_single_or_nan_std_returns_zero_not_degenerate(self) -> None:
        """A single observation (NaN std) must not produce a degenerate ratio.

        After dropping NaNs, an equity path can collapse to a single return
        observation; returns.std() is NaN for a length-1 series, so the
        zero-variance guard must treat non-finite std as undefined variance
        and return 0.0 (matching calculate_sharpe_ratio), not -15.87.
        """
        single = pd.Series([0.0])
        assert not np.isfinite(single.std())
        assert calculate_sortino_ratio(single) == pytest.approx(0.0)
        assert not np.isnan(calculate_sortino_ratio(single))

        # NaN-gapped equity that yields a single flat return via
        # calculate_all_metrics.
        equity = pd.Series([100.0, np.nan, 100.0, 100.0])
        metrics = calculate_all_metrics(equity)
        assert metrics.sortino_ratio == pytest.approx(0.0)
        assert metrics.sharpe_ratio == pytest.approx(0.0)

    def test_non_annualized(self) -> None:
        """annualize=False skips the sqrt(252) scaling (risk/metrics.py:90->92)."""
        non_annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=False)
        annual = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, annualize=True)
        assert non_annual == pytest.approx(annual / np.sqrt(252))

    def test_periods_per_year_used_for_risk_free_and_scaling(self) -> None:
        """The annual risk-free rate and the sqrt scaling must use periods_per_year."""
        mar = 0.02 / 52
        downside_dev = self._downside_deviation(RETURNS, mar)
        expected = (RETURNS.mean() - mar) / downside_dev * np.sqrt(52)
        sortino = calculate_sortino_ratio(RETURNS, risk_free_rate=0.02, periods_per_year=52)
        assert sortino == pytest.approx(expected)


class TestCalculateVar:
    """Tests for calculate_var."""

    def test_var_95(self) -> None:
        result = calculate_var(RETURNS, confidence=0.95)
        assert result == pytest.approx(np.percentile(RETURNS, 5))

    def test_var_99(self) -> None:
        result = calculate_var(RETURNS, confidence=0.99)
        assert result == pytest.approx(np.percentile(RETURNS, 1))

    def test_empty_returns_zero(self) -> None:
        assert calculate_var(pd.Series([], dtype=float)) == pytest.approx(0.0)


class TestCalculateBeta:
    """Tests for calculate_beta."""

    def test_beta_correlation(self) -> None:
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        aligned = pd.concat([RETURNS, MARKET_RETURNS], axis=1).dropna()
        expected = aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / aligned.iloc[:, 1].var()
        assert beta == pytest.approx(expected)

    def test_beta_identical_series_is_one(self) -> None:
        beta = calculate_beta(RETURNS, RETURNS)
        assert beta == pytest.approx(1.0)

    def test_beta_insufficient_samples(self) -> None:
        small = pd.Series([0.01])
        assert calculate_beta(small, MARKET_RETURNS) == pytest.approx(0.0)

    def test_beta_zero_market_variance(self) -> None:
        constant = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        assert calculate_beta(RETURNS, constant) == pytest.approx(0.0)

    def test_beta_non_overlapping_indices_aligns_positionally(self) -> None:
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

    def test_beta_insufficient_aligned_points_after_fallback(self) -> None:
        """Both series have >= 2 points but NaNs leave < 2 aligned -> 0.0 beta.

        Index alignment and the positional fallback both drop the NaN rows,
        leaving too few observations, so beta is 0.0
        (quant_trading/risk/metrics.py:calculate_beta).
        """
        returns = pd.Series([0.01, float("nan")])
        market = pd.Series([0.01, 0.02])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_non_finite_market_variance(self) -> None:
        """A market series with >1 unique value but non-finite variance -> 0.0.

        ``nunique`` treats ``inf`` as a distinct value, so the constant-variance
        guard is bypassed and the explicit ``np.isfinite`` check must return 0.0
        (quant_trading/risk/metrics.py:calculate_beta).
        """
        import warnings

        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.01, np.inf, 0.02])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert calculate_beta(returns, market) == pytest.approx(0.0)


class TestCalculateAlpha:
    """Tests for calculate_alpha."""

    def test_alpha_value(self) -> None:
        alpha = calculate_alpha(RETURNS, MARKET_RETURNS, risk_free_rate=0.02)
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        expected = RETURNS.mean() * 252 - (0.02 + beta * (MARKET_RETURNS.mean() * 252 - 0.02))
        assert alpha == pytest.approx(expected)

    def test_alpha_zero_beta(self) -> None:
        constant = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        assert calculate_alpha(RETURNS, constant) == pytest.approx(0.0)

    def test_alpha_periods_per_year_scales_annualization(self) -> None:
        """Alpha annualization must follow the requested periods per year."""
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        expected = RETURNS.mean() * 12 - (0.02 + beta * (MARKET_RETURNS.mean() * 12 - 0.02))
        alpha = calculate_alpha(RETURNS, MARKET_RETURNS, risk_free_rate=0.02, periods_per_year=12)
        assert alpha == pytest.approx(expected)


class TestCalculateCalmarRatio:
    """Tests for calculate_calmar_ratio."""

    def test_calmar_value(self) -> None:
        equity = pd.Series([100.0, 110.0, 90.0, 95.0, 98.0])
        calmar = calculate_calmar_ratio(RETURNS, equity)
        expected = (RETURNS.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calmar == pytest.approx(expected)

    def test_calmar_no_drawdown_zero(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0])
        assert calculate_calmar_ratio(RETURNS, equity) == pytest.approx(0.0)

    def test_calmar_empty_returns_zero(self) -> None:
        equity = pd.Series([100.0])
        assert calculate_calmar_ratio(pd.Series([], dtype=float), equity) == pytest.approx(0.0)

    def test_calmar_periods_per_year_scales_annual_return(self) -> None:
        """The annualized return in the Calmar ratio must follow periods_per_year."""
        equity = pd.Series([100.0, 110.0, 90.0, 95.0, 98.0])
        expected = (RETURNS.mean() * 12) / abs(calculate_max_drawdown(equity))
        calmar = calculate_calmar_ratio(RETURNS, equity, periods_per_year=12)
        assert calmar == pytest.approx(expected)

    def test_calmar_uses_aligned_sample(self) -> None:
        """Both the return and the drawdown must come from the shared index."""
        returns = pd.Series([0.10, 0.20, -0.50, 0.01], index=list("abcd"))
        equity = pd.Series([100.0, 60.0, 200.0, 150.0], index=list("bcde"))
        # Only b/c/d are shared; 'a' has no equity value and 'e' has no return.
        aligned_returns = returns.loc[["b", "c", "d"]]
        aligned_equity = equity.loc[["b", "c", "d"]]
        expected = (aligned_returns.mean() * 252) / abs(calculate_max_drawdown(aligned_equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(expected)
        # The old raw-mixing result (mean of all returns over the full curve)
        # differs, so this actually exercises the alignment.
        mixed = (returns.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calculate_calmar_ratio(returns, equity) != pytest.approx(mixed)

    def test_calmar_aligns_dropping_nan_rows(self) -> None:
        """A NaN row must drop the observation from both numerator and denominator."""
        equity = pd.Series([100.0, 120.0, float("nan"), 90.0, 80.0], index=list("abcde"))
        returns = pd.Series([0.50, -0.25, -0.111], index=list("cde"))
        aligned_equity = equity.loc[["c", "d", "e"]].dropna()
        aligned_returns = returns.loc[aligned_equity.index]
        expected = (aligned_returns.mean() * 252) / abs(calculate_max_drawdown(aligned_equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(expected)

    def test_calmar_drawdown_includes_bar_that_seeds_first_return(self) -> None:
        """A global peak at the first bar must not be dropped from the drawdown."""
        idx = pd.date_range("2020-01-01", periods=5)
        equity = pd.Series([100.0, 90.0, 80.0, 85.0, 82.0], index=idx)
        returns = calculate_returns(equity)
        # Returns index starts at equity.index[1:], so the first bar is the peak.
        assert calculate_max_drawdown(equity) == pytest.approx(-0.2)
        assert calculate_max_drawdown(equity.iloc[1:]) == pytest.approx(-0.111111, abs=1e-5)
        expected = (returns.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(expected)

    def test_calmar_falls_back_to_positional_when_indices_are_disjoint(self) -> None:
        """Disjoint indices fall back to positional pairing, mirroring _align_series."""
        returns = pd.Series([0.10, 0.20, -0.50], index=list("abc"))
        equity = pd.Series([100.0, 60.0, 200.0], index=list("xyz"))
        expected = (returns.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(expected)

    def test_calmar_returns_zero_with_fewer_than_two_aligned_points(self) -> None:
        returns = pd.Series([0.10], index=["a"])
        equity = pd.Series([100.0], index=["a"])
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(0.0)

    def test_calmar_duplicate_equity_labels_get_loc_branch(self) -> None:
        equity = pd.Series([100.0, 90.0, 80.0, 120.0], index=["a", "a", "b", "b"])
        returns = calculate_returns(equity)
        assert np.isfinite(calculate_calmar_ratio(returns, equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(121.3333333333333)

    def test_calmar_duplicate_labels_get_loc_slice_branch(self) -> None:
        # Contiguous duplicate labels keep label alignment intact (identical
        # indexes), so equity_curve.index.get_loc returns a slice for the first
        # aligned label and the slice/ndarray branch of calculate_calmar_ratio
        # is exercised instead of the positional-fallback or KeyError paths.
        equity = pd.Series([100.0, 90.0, 80.0, 120.0], index=["a", "a", "a", "b"])
        returns = pd.Series([-0.10, -1 / 9, 0.50, 0.05], index=["a", "a", "a", "b"])
        assert np.isfinite(calculate_calmar_ratio(returns, equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(106.75)

    def test_calmar_duplicate_labels_get_loc_ndarray_seed_branch(self) -> None:
        # Non-contiguous duplicate labels make get_loc return an ndarray whose
        # first element is truthy (>0 after int conversion), exercising the
        # seed-bar prepended branch (lines 521-522).
        equity = pd.Series([100.0, 90.0, 80.0, 120.0], index=["a", "b", "a", "b"])
        returns = pd.Series([0.0, -0.1, -0.111, 0.5], index=["a", "b", "a", "b"])
        assert np.isfinite(calculate_calmar_ratio(returns, equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(91.035)

    def test_calmar_no_seed_bar_when_first_aligned_at_position_zero(self) -> None:
        # When the first aligned equity bar is already the first bar of the
        # curve, pos == 0 and the seed-bar prepend branch is skipped.
        idx = pd.date_range("2020-01-01", periods=5)
        equity = pd.Series([100.0, 90.0, 80.0, 85.0, 82.0], index=idx)
        returns = pd.Series([0.0, -0.1, -0.111, 0.0625, -0.0353], index=idx)
        expected = (returns.mean() * 252) / abs(calculate_max_drawdown(equity))
        assert calculate_calmar_ratio(returns, equity) == pytest.approx(expected)


class TestRiskMetricsDataclass:
    """Tests for RiskMetrics container."""

    def test_to_dict_keys(self) -> None:
        metrics = RiskMetrics(
            sharpe_ratio=1.5,
            sortino_ratio=0.8,
            max_drawdown=-0.1,
            volatility=0.2,
            var_95=-0.05,
            var_99=-0.08,
            cvar_95=-0.06,
            cvar_99=-0.10,
            beta=1.1,
            alpha=0.02,
            calmar_ratio=2.3,
            treynor_ratio=0.03,
            information_ratio=0.5,
            omega_ratio=1.8,
        )
        data = metrics.to_dict()
        assert set(data.keys()) == {
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "volatility",
            "var_95",
            "var_99",
            "cvar_95",
            "cvar_99",
            "beta",
            "alpha",
            "calmar_ratio",
            "treynor_ratio",
            "information_ratio",
            "omega_ratio",
            "ulcer_index",
        }
        assert data["sharpe_ratio"] == pytest.approx(1.5)
        assert data["calmar_ratio"] == pytest.approx(2.3)

    def test_defaults(self) -> None:
        metrics = RiskMetrics()
        data = metrics.to_dict()
        assert all(v == 0.0 for v in data.values())

    def test_from_dict_round_trip(self) -> None:
        """from_dict(to_dict(metrics)) restores every field."""
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
        restored = RiskMetrics.from_dict(metrics.to_dict())
        assert restored.sharpe_ratio == pytest.approx(1.5)
        assert restored.sortino_ratio == pytest.approx(0.8)
        assert restored.max_drawdown == pytest.approx(-0.1)
        assert restored.volatility == pytest.approx(0.2)
        assert restored.var_95 == pytest.approx(-0.05)
        assert restored.var_99 == pytest.approx(-0.08)
        assert restored.beta == pytest.approx(1.1)
        assert restored.alpha == pytest.approx(0.02)
        assert restored.calmar_ratio == pytest.approx(2.3)

    def test_from_dict_defaults_missing_fields(self) -> None:
        """from_dict tolerates a dict that omits fields."""
        restored = RiskMetrics.from_dict({"sharpe_ratio": 1.5})
        assert restored.sharpe_ratio == pytest.approx(1.5)
        assert all(
            value == 0.0 for name, value in restored.to_dict().items() if name != "sharpe_ratio"
        )

    def test_from_dict_empty_dict(self) -> None:
        """from_dict tolerates an empty dict."""
        restored = RiskMetrics.from_dict({})
        assert all(v == 0.0 for v in restored.to_dict().values())


class TestCalculateAllMetrics:
    """Tests for calculate_all_metrics orchestration."""

    def test_without_market_returns(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0])
        metrics = calculate_all_metrics(equity, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(0.0)
        assert metrics.alpha == pytest.approx(0.0)
        assert isinstance(metrics.sharpe_ratio, float)
        assert isinstance(metrics.volatility, float)
        assert isinstance(metrics.var_95, float)
        assert metrics.ulcer_index == pytest.approx(calculate_ulcer_index(equity))
        result = metrics.to_dict()
        assert set(result.keys()) == RiskMetrics().to_dict().keys()

    def test_with_market_returns_beta_one(self) -> None:
        idx = pd.date_range("2020-01-01", periods=6)
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0, 118.0], index=idx)
        market = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, market_returns=market, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(1.0)
        assert metrics.alpha == pytest.approx(0.0, abs=1e-9)

    def test_with_market_returns_custom_beta(self) -> None:
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

    def test_periods_per_year_threaded_to_every_metric(self) -> None:
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

    def test_default_periods_per_year_matches_daily_annualization(self) -> None:
        """The default (252) must reproduce the documented daily annualization."""
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0, 112.0, 120.0])
        returns = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, risk_free_rate=0.02)
        assert metrics.volatility == pytest.approx(returns.std() * np.sqrt(252))
        assert metrics.sharpe_ratio == pytest.approx(
            calculate_sharpe_ratio(returns, risk_free_rate=0.02, periods_per_year=252)
        )


class TestEdgeCaseCoverage:
    """Additional edge-case coverage recovered from the legacy __main__ block."""

    def test_var_single_value(self) -> None:
        """Single value returns: percentile behavior should not produce NaN."""
        result = calculate_var(pd.Series([0.01]), confidence=0.95)
        assert not np.isnan(result)
        assert result == pytest.approx(0.01)

    def test_var_single_value_high_confidence(self) -> None:
        """Single value with high confidence."""
        result = calculate_var(pd.Series([-0.05]), confidence=0.99)
        assert not np.isnan(result)
        assert result == pytest.approx(-0.05)

    def test_beta_market_single_value(self) -> None:
        """Market with single value paired with returns < 2 aligned should give 0."""
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.01])  # only 1 value
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_both_single_values(self) -> None:
        returns = pd.Series([0.01])
        market = pd.Series([0.02])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_beta_market_constant_after_alignment(self) -> None:
        returns = pd.Series([0.01, 0.02, 0.03])
        market = pd.Series([0.05, 0.05, 0.05])
        assert calculate_beta(returns, market) == pytest.approx(0.0)

    def test_alpha_insufficient_returns(self) -> None:
        small = pd.Series([0.01])
        market = pd.Series([0.01, 0.02, 0.03])
        assert calculate_alpha(small, market) == pytest.approx(0.0)

    def test_alpha_insufficient_market(self) -> None:
        returns = pd.Series([0.01, 0.02, 0.03])
        small = pd.Series([0.01])
        assert calculate_alpha(returns, small) == pytest.approx(0.0)

    def test_returns_with_nan_dropped(self) -> None:
        prices = pd.Series([1.0, float("nan"), 2.0, 3.0])
        res = calculate_returns(prices)
        assert res.isna().sum() == 0

    def test_returns_all_same_extra(self) -> None:
        prices = pd.Series([1.0, 1.0, 1.0])
        res = calculate_returns(prices)
        assert all(v == 0.0 for v in res)

    def test_returns_two_points_extra(self) -> None:
        prices = pd.Series([1.0, 2.0])
        res = calculate_returns(prices)
        assert len(res) == 1
        assert res.iloc[0] == pytest.approx(1.0)


class TestNanHandling:
    """Tests for NaN handling in risk metrics."""

    def test_var_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_var(r)
        assert not np.isnan(res)
        assert res < 0

    def test_volatility_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        res = calculate_volatility(r)
        assert not np.isnan(res)
        assert res > 0

    def test_sharpe_ratio_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, 0.03])
        res = calculate_sharpe_ratio(r)
        assert not np.isnan(res)

    def test_sortino_ratio_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01, -0.02])
        res = calculate_sortino_ratio(r)
        assert not np.isnan(res)

    def test_max_drawdown_with_nans(self) -> None:
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 100.0])
        res = calculate_max_drawdown(eq)
        assert not np.isnan(res)

    def test_beta_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_beta(r, m)
        assert not np.isnan(res)

    def test_alpha_with_nans(self) -> None:
        r = pd.Series([0.01, float("nan"), 0.02, -0.01])
        m = pd.Series([0.005, 0.01, float("nan"), -0.005])
        res = calculate_alpha(r, m)
        assert not np.isnan(res)

    def test_calmar_ratio_with_nans(self) -> None:
        eq = pd.Series([100.0, float("nan"), 110.0, 105.0, 90.0])
        r = calculate_returns(eq)
        res = calculate_calmar_ratio(r, eq)
        assert not np.isnan(res)

    def test_all_metrics_with_nans_in_equity(self) -> None:
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

    def test_alpha_uses_aligned_sample_with_misaligned_indices(self) -> None:
        """Alpha must average the same aligned observations used for beta."""
        returns = pd.Series([0.01, 0.02, 0.03], index=[0, 1, 2])
        market = pd.Series([0.01, 0.02, 0.03], index=[1, 2, 3])

        beta = calculate_beta(returns, market)
        aligned = pd.concat([returns, market], axis=1).dropna()
        expected = aligned.iloc[:, 0].mean() * 252 - (
            0.02 + beta * (aligned.iloc[:, 1].mean() * 252 - 0.02)
        )

        assert calculate_alpha(returns, market) == pytest.approx(expected)

    def test_alpha_non_overlapping_indices_returns_zero(self) -> None:
        """Completely disjoint indices yield no aligned sample -> alpha 0."""
        returns = pd.Series([0.01, 0.02, 0.03], index=[0, 1, 2])
        market = pd.Series([0.01, 0.02, 0.03], index=[3, 4, 5])
        assert calculate_alpha(returns, market) == pytest.approx(0.0)

    def test_alpha_partial_overlap_uses_only_aligned_points(self) -> None:
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

    def test_alpha_consistent_with_beta_in_calculate_all_metrics(self) -> None:
        """calculate_all_metrics must report alpha consistent with its beta."""
        idx = pd.date_range("2020-01-01", periods=6)
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0, 118.0], index=idx)
        market = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, market_returns=market, risk_free_rate=0.02)

        expected_alpha = calculate_alpha(calculate_returns(equity), market, risk_free_rate=0.02)
        assert metrics.alpha == pytest.approx(expected_alpha)
        assert metrics.beta == pytest.approx(calculate_beta(calculate_returns(equity), market))

    def test_alpha_nan_in_market_dropped_before_alignment(self) -> None:
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


class TestCalculateTreynorRatio:
    """Tests for calculate_treynor_ratio."""

    def test_treynor_basic(self) -> None:
        treynor = calculate_treynor_ratio(RETURNS, MARKET_RETURNS, risk_free_rate=0.02)
        beta = calculate_beta(RETURNS, MARKET_RETURNS)
        expected = (RETURNS.mean() - 0.02 / 252) / beta * 252
        assert treynor == pytest.approx(expected)

    def test_treynor_zero_beta(self) -> None:
        constant = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        assert calculate_treynor_ratio(RETURNS, constant) == pytest.approx(0.0)

    def test_treynor_insufficient_returns(self) -> None:
        small = pd.Series([0.01])
        assert calculate_treynor_ratio(small, MARKET_RETURNS) == pytest.approx(0.0)

    def test_treynor_periods_per_year_scales(self) -> None:
        daily = calculate_treynor_ratio(RETURNS, MARKET_RETURNS, risk_free_rate=0.02)
        monthly = calculate_treynor_ratio(
            RETURNS, MARKET_RETURNS, risk_free_rate=0.02, periods_per_year=12
        )
        assert monthly != pytest.approx(daily)

    def test_treynor_uses_aligned_sample(self) -> None:
        """Treynor uses the same aligned sample as beta, not the raw returns."""
        index = pd.date_range("2024-01-01", periods=4)
        returns = pd.Series([0.01, 0.02, 0.5, 0.004], index=index)
        market = pd.Series([0.008, np.nan, 0.004, 0.002], index=index)
        beta = calculate_beta(returns, market)
        aligned = _align_series(returns, market)
        expected = (aligned.iloc[:, 0].mean() * 252 - 0.02) / beta
        assert calculate_treynor_ratio(returns, market) == pytest.approx(expected)
        unaligned = (returns.mean() * 252 - 0.02) / beta
        assert calculate_treynor_ratio(returns, market) != pytest.approx(unaligned)


class TestCalculateInformationRatio:
    """Tests for calculate_information_ratio."""

    def test_information_ratio_basic(self) -> None:
        info = calculate_information_ratio(RETURNS, MARKET_RETURNS)
        aligned = _align_series(RETURNS, MARKET_RETURNS)
        active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
        expected = active.mean() / active.std() * np.sqrt(252)
        assert info == pytest.approx(expected)

    def test_information_ratio_identical_series(self) -> None:
        assert calculate_information_ratio(RETURNS, RETURNS) == pytest.approx(0.0)

    def test_information_ratio_zero_tracking_error(self) -> None:
        constant = pd.Series([0.01, 0.01, 0.01, 0.01, 0.01])
        assert calculate_information_ratio(RETURNS, constant) == pytest.approx(0.0)

    def test_information_ratio_insufficient_aligned(self) -> None:
        small = pd.Series([0.01])
        assert calculate_information_ratio(small, MARKET_RETURNS) == pytest.approx(0.0)

    def test_information_ratio_periods_per_year_scales(self) -> None:
        daily = calculate_information_ratio(RETURNS, MARKET_RETURNS)
        monthly = calculate_information_ratio(RETURNS, MARKET_RETURNS, periods_per_year=12)
        assert monthly == pytest.approx(daily * np.sqrt(12 / 252))

    def test_information_ratio_duplicate_labels_finite(self) -> None:
        returns = pd.Series([0.01, 0.02, 0.03, 0.04], index=["a", "b", "b", "c"])
        benchmark = pd.Series([0.01, 0.02, 0.03, 0.04], index=["a", "a", "b", "c"])
        assert np.isfinite(calculate_information_ratio(returns, benchmark))


class TestCalculateCVaR:
    """Tests for calculate_cvar (Conditional VaR / Expected Shortfall)."""

    def test_cvar_95(self) -> None:
        cvar = calculate_cvar(RETURNS, confidence=0.95)
        var_95 = np.percentile(RETURNS, 5)
        tail = RETURNS[RETURNS <= var_95]
        expected = tail.mean()
        assert cvar == pytest.approx(expected)
        assert cvar <= var_95  # CVaR should be <= VaR (more negative)

    def test_cvar_99(self) -> None:
        cvar = calculate_cvar(RETURNS, confidence=0.99)
        var_99 = np.percentile(RETURNS, 1)
        tail = RETURNS[RETURNS <= var_99]
        expected = tail.mean()
        assert cvar == pytest.approx(expected)
        assert cvar <= var_99

    def test_cvar_empty_returns_zero(self) -> None:
        assert calculate_cvar(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_cvar_single_value(self) -> None:
        result = calculate_cvar(pd.Series([-0.05]), confidence=0.95)
        assert result == pytest.approx(-0.05)

    def test_cvar_all_same_returns(self) -> None:
        flat = pd.Series([0.01] * 10)
        cvar = calculate_cvar(flat, confidence=0.95)
        assert cvar == pytest.approx(0.01)


class TestCalculateOmegaRatio:
    """Tests for calculate_omega_ratio."""

    def test_omega_basic(self) -> None:
        returns = pd.Series([0.01, 0.02, -0.005, 0.015, -0.01])
        omega = calculate_omega_ratio(returns, threshold=0.0)
        gains = np.sum(np.maximum(returns - 0.0, 0.0))
        losses = np.sum(np.maximum(0.0 - returns, 0.0))
        expected = gains / losses
        assert omega == pytest.approx(expected)

    def test_omega_custom_threshold(self) -> None:
        returns = pd.Series([0.01, 0.02, -0.005, 0.015, -0.01])
        omega = calculate_omega_ratio(returns, threshold=0.01)
        gains = np.sum(np.maximum(returns - 0.01, 0.0))
        losses = np.sum(np.maximum(0.01 - returns, 0.0))
        expected = gains / losses
        assert omega == pytest.approx(expected)

    def test_omega_no_losses(self) -> None:
        positive = pd.Series([0.01, 0.02, 0.03])
        assert calculate_omega_ratio(positive, threshold=0.0) == pytest.approx(0.0)

    def test_omega_empty_returns_zero(self) -> None:
        assert calculate_omega_ratio(pd.Series([], dtype=float)) == pytest.approx(0.0)

    def test_omega_all_losses(self) -> None:
        negative = pd.Series([-0.01, -0.02, -0.03])
        omega = calculate_omega_ratio(negative, threshold=0.0)
        gains = np.sum(np.maximum(negative - 0.0, 0.0))
        losses = np.sum(np.maximum(0.0 - negative, 0.0))
        expected = gains / losses
        assert omega == pytest.approx(expected)


class TestRiskMetricsDataclassExtended:
    """Tests for RiskMetrics container with new fields."""

    def test_to_dict_includes_new_fields(self) -> None:
        metrics = RiskMetrics(
            sharpe_ratio=1.5,
            sortino_ratio=0.8,
            max_drawdown=-0.1,
            volatility=0.2,
            var_95=-0.05,
            var_99=-0.08,
            cvar_95=-0.06,
            cvar_99=-0.10,
            beta=1.1,
            alpha=0.02,
            calmar_ratio=2.3,
            treynor_ratio=0.03,
            information_ratio=0.5,
            omega_ratio=1.8,
            ulcer_index=0.07,
        )
        data = metrics.to_dict()
        assert "cvar_95" in data
        assert "cvar_99" in data
        assert "treynor_ratio" in data
        assert "information_ratio" in data
        assert "omega_ratio" in data
        assert "ulcer_index" in data
        assert data["cvar_95"] == pytest.approx(-0.06)
        assert data["cvar_99"] == pytest.approx(-0.10)
        assert data["treynor_ratio"] == pytest.approx(0.03)
        assert data["information_ratio"] == pytest.approx(0.5)
        assert data["omega_ratio"] == pytest.approx(1.8)
        assert data["ulcer_index"] == pytest.approx(0.07)

    def test_from_dict_round_trip_new_fields(self) -> None:
        metrics = RiskMetrics(
            cvar_95=-0.06,
            cvar_99=-0.10,
            treynor_ratio=0.03,
            information_ratio=0.5,
            omega_ratio=1.8,
            ulcer_index=0.07,
        )
        restored = RiskMetrics.from_dict(metrics.to_dict())
        assert restored.cvar_95 == pytest.approx(-0.06)
        assert restored.cvar_99 == pytest.approx(-0.10)
        assert restored.treynor_ratio == pytest.approx(0.03)
        assert restored.information_ratio == pytest.approx(0.5)
        assert restored.omega_ratio == pytest.approx(1.8)
        assert restored.ulcer_index == pytest.approx(0.07)

    def test_from_dict_defaults_new_fields(self) -> None:
        restored = RiskMetrics.from_dict({"sharpe_ratio": 1.5})
        assert restored.cvar_95 == 0.0
        assert restored.cvar_99 == 0.0
        assert restored.treynor_ratio == 0.0
        assert restored.information_ratio == 0.0
        assert restored.omega_ratio == 0.0
        assert restored.ulcer_index == 0.0


class TestCalculateAllMetricsExtended:
    """Tests for calculate_all_metrics with new fields."""

    def test_without_market_returns_includes_cvar_omega(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0])
        metrics = calculate_all_metrics(equity, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(0.0)
        assert metrics.alpha == pytest.approx(0.0)
        assert metrics.treynor_ratio == pytest.approx(0.0)
        assert metrics.information_ratio == pytest.approx(0.0)
        assert isinstance(metrics.cvar_95, float)
        assert isinstance(metrics.cvar_99, float)
        assert isinstance(metrics.omega_ratio, float)
        assert isinstance(metrics.ulcer_index, float)
        assert metrics.cvar_95 <= metrics.var_95
        assert metrics.cvar_99 <= metrics.var_99
        assert metrics.ulcer_index >= 0.0

    def test_with_market_returns_includes_treynor_info(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0, 118.0])
        market = calculate_returns(equity)
        metrics = calculate_all_metrics(equity, market_returns=market, risk_free_rate=0.02)
        assert metrics.beta == pytest.approx(1.0)
        assert metrics.treynor_ratio != 0.0
        assert metrics.information_ratio == pytest.approx(0.0)
        assert metrics.ulcer_index == pytest.approx(calculate_ulcer_index(equity))

    def test_periods_per_year_threaded_to_new_metrics(self) -> None:
        equity = pd.Series([100.0, 105.0, 110.0, 108.0, 115.0, 112.0, 120.0])
        market = pd.Series([100.0, 102.0, 104.0, 103.0, 107.0, 109.0, 111.0])
        metrics = calculate_all_metrics(
            equity,
            market_returns=calculate_returns(market),
            risk_free_rate=0.02,
            periods_per_year=52,
        )
        assert metrics.treynor_ratio == pytest.approx(
            calculate_treynor_ratio(
                calculate_returns(equity),
                calculate_returns(market),
                risk_free_rate=0.02,
                periods_per_year=52,
            )
        )
        assert metrics.information_ratio == pytest.approx(
            calculate_information_ratio(
                calculate_returns(equity),
                calculate_returns(market),
                periods_per_year=52,
            )
        )


class TestAlignSeries:
    """Tests for _align_series alignment and duplicate-index positional fallback."""

    def test_duplicate_indices_both_series_positional_fallback(self) -> None:
        # Both series carry duplicate labels; index alignment would produce a
        # cartesian expansion (4 rows for label "a" + 1 for "b" = 5 rows),
        # so _align_series must fall back to positional pairing by row.
        returns = pd.Series([0.01, 0.02, 0.03], index=["a", "a", "b"])
        market = pd.Series([0.10, 0.20, 0.30], index=["a", "a", "b"])
        aligned = _align_series(returns, market)
        expected = pd.DataFrame({0: [0.01, 0.02, 0.03], 1: [0.10, 0.20, 0.30]})
        pd.testing.assert_frame_equal(aligned.reset_index(drop=True), expected)

    def test_positional_fallback_pairs_by_position_not_label(self) -> None:
        # Duplicate labels must not pair observations sharing a label across
        # rows; each observation pairs with the one at the same position.
        returns = pd.Series([1.0, 2.0, 3.0], index=["x", "x", "y"])
        market = pd.Series([4.0, 5.0, 6.0], index=["x", "x", "y"])
        aligned = _align_series(returns, market)
        assert aligned.shape == (3, 2)
        assert aligned.iloc[:, 0].tolist() == [1.0, 2.0, 3.0]
        assert aligned.iloc[:, 1].tolist() == [4.0, 5.0, 6.0]

    def test_duplicate_labels_in_one_series_fall_back_instead_of_raising(self) -> None:
        # A duplicate label on one side only would make label alignment grow
        # the frame or raise "cannot reindex on an axis with duplicate
        # labels"; the helper must pair rows positionally instead.
        returns = pd.Series([0.01, 0.02, 0.03], index=["a", "a", "b"])
        market = pd.Series([0.10, 0.20, 0.30], index=["a", "b", "c"])
        aligned = _align_series(returns, market)
        expected = pd.DataFrame({0: [0.01, 0.02, 0.03], 1: [0.10, 0.20, 0.30]})
        pd.testing.assert_frame_equal(aligned.reset_index(drop=True), expected)

    def test_duplicate_equity_labels_do_not_break_beta(self) -> None:
        # Duplicate date labels are realistic for resampled data; the metric
        # path must stay finite instead of propagating a reindex ValueError.
        returns = pd.Series([0.01, 0.02, 0.03, 0.04], index=["a", "b", "b", "c"])
        market = pd.Series([0.01, 0.02, 0.03, 0.04], index=["a", "a", "b", "c"])
        assert np.isfinite(calculate_beta(returns, market))


class TestNonFiniteInputHandling:
    """Non-finite observations must not contaminate scalar risk metrics."""

    @pytest.mark.parametrize(
        "series",
        [
            pd.Series([np.inf, 0.1, 0.2, 0.3]),
            pd.Series([-np.inf, 0.1, 0.2, 0.3]),
            pd.Series([np.inf, -np.inf, 0.1, 0.2]),
        ],
        ids=["positive_inf", "negative_inf", "both_inf"],
    )
    @pytest.mark.parametrize(
        "metric",
        [
            calculate_volatility,
            lambda returns: calculate_var(returns, confidence=0.95),
            lambda returns: calculate_var(returns, confidence=0.99),
            lambda returns: calculate_cvar(returns, confidence=0.95),
            lambda returns: calculate_cvar(returns, confidence=0.99),
            calculate_omega_ratio,
        ],
        ids=["volatility", "var95", "var99", "cvar95", "cvar99", "omega"],
    )
    def test_return_metrics_ignore_non_finite_values(self, series: pd.Series, metric: Any) -> None:
        assert np.isfinite(metric(series))

    @pytest.mark.parametrize(
        "metric",
        [
            calculate_beta,
            calculate_alpha,
            calculate_treynor_ratio,
            calculate_information_ratio,
        ],
        ids=["beta", "alpha", "treynor", "information"],
    )
    def test_market_relative_metrics_ignore_non_finite_returns(self, metric: Any) -> None:
        returns = pd.Series([np.inf, 0.01, 0.02, 0.03])
        market = pd.Series([0.01, 0.02, 0.03, 0.04])
        assert np.isfinite(metric(returns, market))

    def test_all_metrics_ignore_non_finite_equity_and_benchmark_values(self) -> None:
        equity = pd.Series([100.0, np.inf, np.nan, 90.0, 110.0])
        market = pd.Series([0.01, np.inf, 0.02, np.nan, 0.03])
        metrics = calculate_all_metrics(equity, market_returns=market)
        assert all(np.isfinite(value) for value in metrics.to_dict().values())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
