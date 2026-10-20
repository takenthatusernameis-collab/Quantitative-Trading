"""Tests for the risk manager."""

import pandas as pd
import pytest

from quant_trading.risk.limits import CheckResult
from quant_trading.risk.manager import PortfolioRisk, RiskManager
from quant_trading.risk.metrics import RiskMetrics
from quant_trading.strategies.base import Position, Signal


class TestRiskManagerInit:
    """Tests for RiskManager initialization."""

    def test_default_initialization(self):
        rm = RiskManager()
        assert rm.initial_capital == 100000.0
        assert rm.risk_enabled is True
        assert rm.risk_metrics is None
        assert rm.peak_value == 100000.0
        assert rm.positions == {}
        assert rm.equity_curve == [100000.0]
        assert rm.history == []
        assert rm.portfolio_risk.total_market_value == 100000.0
        assert rm.portfolio_risk.cash == 100000.0
        assert rm.portfolio_risk.peak_value == 100000.0

    def test_custom_initialization(self):
        rm = RiskManager(
            initial_capital=50000.0,
            max_position_size=0.2,
            max_portfolio_risk=0.05,
            max_drawdown=0.30,
            max_positions=5,
            stop_loss_pct=0.10,
            take_profit_pct=0.25,
        )
        assert rm.initial_capital == 50000.0
        assert rm.position_limit.max_size == 0.2
        assert rm.position_limit.max_value == 10000.0
        assert rm.position_limit.stop_loss_pct == 0.10
        assert rm.position_limit.take_profit_pct == 0.25
        assert rm.portfolio_limit.max_positions == 5
        assert rm.portfolio_limit.max_portfolio_risk == 0.05
        assert rm.portfolio_limit.max_drawdown == 0.30
        assert rm.portfolio_risk.total_market_value == 50000.0

    def test_portfolio_risk_total_value_property(self):
        rm = RiskManager(initial_capital=100000.0)
        assert rm.portfolio_risk.total_value == rm.portfolio_risk.total_market_value == 100000.0

    def test_portfolio_limit_receives_stop_loss_pct(self):
        """The stop loss distance is shared with the portfolio risk limit."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10)
        assert rm.portfolio_limit.stop_loss_pct == 0.10

    def test_portfolio_limit_receives_max_leverage(self):
        """The leverage limit is forwarded to the portfolio limit."""
        rm = RiskManager(initial_capital=100000.0, max_leverage=2.5)
        assert rm.portfolio_limit.max_leverage == 2.5


class TestUpdatePortfolioValue:
    """Tests for update_portfolio_value."""

    def test_update_with_empty_positions(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 100000.0)
        assert rm.portfolio_risk.positions_value == 0.0
        assert rm.portfolio_risk.total_market_value == 100000.0
        assert rm.portfolio_risk.leverage == 0.0
        assert rm.portfolio_risk.current_drawdown == 0.0
        assert rm.equity_curve == [100000.0, 100000.0]
        assert rm.peak_value == 100000.0
        assert len(rm.history) == 1

    def test_update_with_positions(self):
        rm = RiskManager(initial_capital=100000.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        rm.update_portfolio_value(positions, 24000.0)
        assert rm.portfolio_risk.positions_value == 16000.0
        assert rm.portfolio_risk.total_market_value == 40000.0
        assert rm.portfolio_risk.leverage == pytest.approx(0.4)
        assert rm.portfolio_risk.current_drawdown == pytest.approx((40000 - 100000) / 100000)
        assert rm.equity_curve[-1] == 40000.0
        assert len(rm.history) == 1

    def test_update_tracks_drawdown_and_peak(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 120000.0)
        assert rm.peak_value == 120000.0
        # A new high is not a drawdown. The drawdown is measured against the
        # peak the portfolio is actually at, so it is 0.0 at the peak.
        assert rm.portfolio_risk.current_drawdown == 0.0
        assert rm.portfolio_risk.peak_value == 120000.0
        rm.update_portfolio_value({}, 90000.0)
        assert rm.peak_value == 120000.0
        assert rm.portfolio_risk.current_drawdown == pytest.approx((90000 - 120000) / 120000)

    def test_update_at_new_peak_reports_no_drawdown(self):
        """A portfolio at a new high reports a zero drawdown, never a positive one."""
        rm = RiskManager(initial_capital=100000.0)
        for value in (120000.0, 150000.0, 200000.0):
            rm.update_portfolio_value({}, value)
            assert rm.portfolio_risk.current_drawdown == 0.0
            assert rm.portfolio_risk.peak_value == value
            assert rm.peak_value == value
            assert rm.history[-1]["drawdown"] == 0.0

    def test_update_reports_drawdown_below_the_peak(self):
        """Below the peak the drawdown is negative and matches the peak."""
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 120000.0)
        rm.update_portfolio_value({}, 90000.0)
        assert rm.portfolio_risk.current_drawdown == pytest.approx((90000 - 120000) / 120000)
        assert rm.portfolio_risk.current_drawdown < 0.0
        assert rm.portfolio_risk.peak_value == 120000.0

    def test_update_zero_value_no_leverage(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 0.0)
        assert rm.portfolio_risk.leverage == 0.0
        assert rm.portfolio_risk.current_drawdown == pytest.approx((0 - 100000) / 100000)


class TestCheckSignal:
    """Tests for check_signal."""

    def test_risk_disabled_returns_passed(self):
        rm = RiskManager()
        rm.disable()
        signal = Signal(symbol="AAPL", action="buy", price=150.0)
        result = rm.check_signal(signal)
        assert isinstance(result, CheckResult)
        assert result.passed is True
        assert result.violations == []

    def test_portfolio_value_zero_or_negative(self):
        rm = RiskManager()
        signal = Signal(symbol="AAPL", action="buy", price=150.0)
        result = rm.check_signal(signal, portfolio_value=-1.0)
        assert result.passed is False
        assert any("zero or negative" in v for v in result.violations)

    def test_explicit_zero_portfolio_value_is_rejected(self):
        """An explicit portfolio value of 0.0 is rejected, not treated as unset.

        The internal portfolio value is only used when the argument is None,
        so a wiped-out portfolio is caught by the zero-value guard.
        """
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 100000.0)
        signal = Signal(symbol="AAPL", action="buy", price=150.0)
        result = rm.check_signal(signal, portfolio_value=0.0)
        assert result.passed is False
        assert any("zero or negative" in v for v in result.violations)

    def test_missing_portfolio_value_uses_the_internal_value(self):
        """A None portfolio value falls back to the manager's own value."""
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 100000.0)
        signal = Signal(symbol="AAPL", action="buy", price=150.0, strength=1.0)
        result = rm.check_signal(signal, portfolio_value=None)
        assert result.passed is True
        assert result.violations == []

    def test_buy_no_price(self):
        rm = RiskManager()
        rm.positions = {}
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=None)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("no price" in v for v in result.violations)

    def test_buy_within_limits(self):
        rm = RiskManager(initial_capital=100000.0)
        signal = Signal(symbol="AAPL", action="buy", strength=0.5, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_buy_exceeds_max_position_value(self):
        rm = RiskManager(initial_capital=100000.0)
        signal = Signal(symbol="AAPL", action="buy", strength=2.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max position value" in v for v in result.violations)
        assert any("exceed max position size" in v for v in result.violations)

    def test_buy_exceeds_max_position_size_only(self):
        rm = RiskManager(initial_capital=100000.0)
        signal = Signal(symbol="AAPL", action="buy", strength=1.1, price=150.0)
        result = rm.check_signal(signal, portfolio_value=50000.0)
        assert result.passed is False
        assert any("exceed max position size" in v for v in result.violations)
        assert not any("exceed max position value" in v for v in result.violations)

    def test_buy_with_existing_position(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=150, current_price=160)
        }
        signal = Signal(symbol="AAPL", action="buy", strength=0.5, price=160.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max position value" in v for v in result.violations)

    def test_sell_no_holdings(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {}
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("no holdings" in v for v in result.violations)

    def test_sell_with_holdings(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_hold_signal_passes(self):
        rm = RiskManager(initial_capital=100000.0)
        signal = Signal(symbol="AAPL", action="hold", price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_buy_exceeds_portfolio_risk_budget(self):
        """A buy that would push open risk above the budget is rejected at the signal gate."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_portfolio_risk=0.02,
            max_position_size=1.0,
            max_leverage=10.0,
            stop_loss_pct=0.05,
        )
        # Existing 200 AAPL @ 150 -> risk 1.5% of 100000, leaving little budget.
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max portfolio risk" in v for v in result.violations)

    def test_buy_exceeds_leverage_limit(self):
        """A buy that would push gross exposure above the leverage limit is rejected at the signal gate."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_portfolio_risk=1.0,
            max_position_size=1.0,
            max_leverage=1.0,
            stop_loss_pct=0.05,
        )
        # Existing 400 AAPL @ 150 -> gross 60000 = 0.6x leverage.
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max leverage" in v for v in result.violations)


class TestCheckPortfolio:
    """Tests for check_portfolio."""

    def test_risk_disabled(self):
        rm = RiskManager()
        rm.disable()
        assert rm.check_portfolio().passed is True

    def test_no_violations(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {}
        assert rm.check_portfolio().passed is True

    def test_too_many_positions(self):
        rm = RiskManager(initial_capital=100000.0, max_positions=1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=1, avg_price=100, current_price=100),
            "MSFT": Position(symbol="MSFT", quantity=1, avg_price=100, current_price=100),
        }
        result = rm.check_portfolio()
        assert result.passed is False
        assert any("exceeds max" in v for v in result.violations)

    def test_drawdown_violation(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {}
        rm.portfolio_risk = PortfolioRisk(
            total_market_value=70000.0, cash=70000.0, peak_value=100000.0
        )
        rm.peak_value = 100000.0
        result = rm.check_portfolio()
        assert result.passed is False
        assert any("Drawdown" in v for v in result.violations)

    def test_uses_default_max_drawdown(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {}
        rm.portfolio_risk = PortfolioRisk(
            total_market_value=90000.0, cash=90000.0, peak_value=100000.0
        )
        rm.peak_value = 100000.0
        result = rm.check_portfolio()
        assert result.passed is True

    def test_leverage_violation(self):
        """Gross exposure above the leverage limit fails the portfolio check."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_leverage=1.0,
            max_position_size=1.0,
            max_portfolio_risk=0.5,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=200, avg_price=300.0, current_price=300.0),
        }
        result = rm.check_portfolio()
        assert result.passed is False
        assert any("Portfolio leverage 1.20x" in v for v in result.violations)

    def test_portfolio_risk_violation(self):
        """Open risk above the risk budget fails the portfolio check."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_portfolio_risk=0.02,
            max_position_size=1.0,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
        }
        result = rm.check_portfolio()
        assert result.passed is False
        assert any("Portfolio risk 3.00%" in v for v in result.violations)

    def test_portfolio_risk_uses_configured_stop_loss(self):
        """The risk budget is sized with the configured stop loss distance."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_portfolio_risk=0.02,
            max_position_size=1.0,
            stop_loss_pct=0.10,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=150.0),
        }
        result = rm.check_portfolio()
        assert result.passed is False
        assert any("Portfolio risk 3.00%" in v for v in result.violations)


class TestCalculateMetrics:
    """Tests for calculate_metrics."""

    def test_calculate_metrics_without_market_returns(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 110000.0)
        rm.update_portfolio_value({}, 105000.0)
        metrics = rm.calculate_metrics()
        assert isinstance(metrics, RiskMetrics)
        assert rm.risk_metrics is metrics
        assert metrics.beta == 0.0
        assert metrics.alpha == 0.0

    def test_calculate_metrics_with_market_returns(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 110000.0)
        rm.update_portfolio_value({}, 105000.0)
        market_returns = pd.Series([0.02, -0.03], index=[1, 2])
        metrics = rm.calculate_metrics(market_returns)
        assert isinstance(metrics, RiskMetrics)
        assert isinstance(metrics.beta, float)
        assert isinstance(metrics.alpha, float)


class TestRiskFreeRate:
    """Tests for the risk_free_rate handling in RiskManager."""

    def test_init_stores_risk_free_rate(self):
        rm = RiskManager(risk_free_rate=0.05)
        assert rm.risk_free_rate == 0.05

    def test_default_risk_free_rate_is_002(self):
        rm = RiskManager()
        assert rm.risk_free_rate == 0.02

    def test_calculate_metrics_uses_configured_rate(self):
        """A non-default risk-free rate must reach the computed Sharpe/Sortino."""
        rm_default = RiskManager(initial_capital=100000.0)
        rm_high = RiskManager(initial_capital=100000.0, risk_free_rate=0.10)

        # Build an equity curve with several up and down moves so both the
        # Sharpe and the Sortino have non-zero denominators.
        for value in (
            100000.0,
            105000.0,
            102000.0,
            108000.0,
            104000.0,
            110000.0,
            107000.0,
            109000.0,
            106000.0,
            108000.0,
        ):
            rm_default.update_portfolio_value({}, value)
            rm_high.update_portfolio_value({}, value)

        default_metrics = rm_default.calculate_metrics()
        high_metrics = rm_high.calculate_metrics()

        # A higher risk-free rate lowers the excess return, so the Sharpe
        # and Sortino must differ from the default-rate computation.
        assert default_metrics.sharpe_ratio != 0.0
        assert default_metrics.sortino_ratio != 0.0
        assert high_metrics.sharpe_ratio != pytest.approx(default_metrics.sharpe_ratio)
        assert high_metrics.sortino_ratio != pytest.approx(default_metrics.sortino_ratio)

    def test_calculate_metrics_explicit_argument_overrides_config(self):
        """An explicit risk_free_rate argument overrides the configured rate."""
        rm = RiskManager(initial_capital=100000.0, risk_free_rate=0.10)
        rm.update_portfolio_value({}, 110000.0)
        rm.update_portfolio_value({}, 105000.0)

        from quant_trading.risk.metrics import calculate_all_metrics

        equity_series = pd.Series(rm.equity_curve)
        expected = calculate_all_metrics(equity_series, risk_free_rate=0.01, periods_per_year=252)

        metrics = rm.calculate_metrics(risk_free_rate=0.01)
        assert metrics.sharpe_ratio == pytest.approx(expected.sharpe_ratio)
        assert metrics.sortino_ratio == pytest.approx(expected.sortino_ratio)


class TestStopLossTakeProfit:
    """Tests for stop-loss and take-profit helpers."""

    def test_get_position_stop_loss_no_position(self):
        rm = RiskManager(stop_loss_pct=0.05)
        rm.positions = {}
        assert rm.get_position_stop_loss("AAPL") is None

    def test_get_position_stop_loss_zero_avg_price(self):
        rm = RiskManager(stop_loss_pct=0.05)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=0.0, current_price=160)
        }
        assert rm.get_position_stop_loss("AAPL") is None

    def test_get_position_stop_loss(self):
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        assert rm.get_position_stop_loss("AAPL") == 150 * 0.9

    def test_should_stop_loss_triggered(self):
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        assert rm.should_stop_loss("AAPL", 130.0) is True
        assert rm.should_stop_loss("AAPL", 200.0) is False
        assert rm.should_stop_loss("UNKNOWN", 100.0) is False

    def test_get_position_take_profit_no_position(self):
        rm = RiskManager(take_profit_pct=0.15)
        rm.positions = {}
        assert rm.get_position_take_profit("AAPL") is None

    def test_get_position_take_profit(self):
        rm = RiskManager(initial_capital=100000.0, take_profit_pct=0.15)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        assert rm.get_position_take_profit("AAPL") == 150 * 1.15

    def test_should_take_profit_triggered(self):
        rm = RiskManager(initial_capital=100000.0, take_profit_pct=0.15)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        assert rm.should_take_profit("AAPL", 200.0) is True
        assert rm.should_take_profit("AAPL", 160.0) is False
        assert rm.should_take_profit("UNKNOWN", 200.0) is False


class TestResetEnableDisable:
    """Tests for reset, enable, and disable."""

    def test_enable_disable(self):
        rm = RiskManager()
        rm.disable()
        assert rm.risk_enabled is False
        rm.enable()
        assert rm.risk_enabled is True

    def test_reset_clears_state(self):
        rm = RiskManager(initial_capital=100000.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160)
        }
        rm.update_portfolio_value(positions, 24000.0)
        assert rm.equity_curve != [100000.0]
        assert rm.positions != {}
        rm.reset()
        assert rm.positions == {}
        assert rm.equity_curve == [100000.0]
        assert rm.peak_value == 100000.0
        assert rm.history == []
        assert rm.portfolio_risk.total_market_value == 100000.0
        assert rm.portfolio_risk.peak_value == 100000.0
        assert rm.risk_metrics is None

    def test_reset_clears_computed_metrics(self):
        """Metrics computed before a reset describe the discarded equity curve."""
        rm = RiskManager(initial_capital=100000.0)
        rm.update_portfolio_value({}, 50000.0)
        rm.calculate_metrics()
        assert rm.risk_metrics is not None
        rm.reset()
        assert rm.risk_metrics is None

    def test_disable_during_check_signal(self):
        rm = RiskManager(initial_capital=100000.0, max_position_size=0.01)
        rm.disable()
        signal = Signal(symbol="AAPL", action="buy", strength=10.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
