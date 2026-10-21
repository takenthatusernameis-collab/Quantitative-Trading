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

    def test_short_position_reports_gross_leverage(self):
        rm = RiskManager(initial_capital=100000.0)
        positions = {"AAPL": Position("AAPL", -100, 150.0, 152.0)}
        rm.update_portfolio_value(positions, 50000.0)
        mv = positions["AAPL"].market_value
        total = 50000.0 + mv
        assert rm.portfolio_risk.leverage == pytest.approx(abs(mv) / total)
        assert rm.portfolio_risk.leverage > 0


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

    def test_buy_with_an_oversized_existing_position(self):
        """A position that is already over the position limit is reported.

        The exposure is measured after the trade, so a position that is
        already above the limit is reported even when the signal would not
        add any exposure to it.
        """
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=150)
        }
        signal = Signal(symbol="AAPL", action="buy", strength=0.5, price=150.0)
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


class TestMaxPositionsGate:
    """The signal gate enforces the number of open positions before a trade.

    ``max_positions`` is the only one of the four portfolio limits that was
    not checked before a trade: the position size, the risk budget and the
    leverage limit are all gated in :meth:`RiskManager.check_signal`, but the
    number of open positions was only detected after the bar by the
    report-only :meth:`RiskManager.check_portfolio`. A ``"buy"`` or a
    ``"short"`` that would open a **new** position is now rejected when the
    portfolio already holds ``max_positions`` positions.

    A signal that tops up a position that is already open does not add a
    position and stays allowed, and a ``"buy"`` that covers an open short
    reduces the gross exposure instead of adding a position, so both stay
    allowed too.
    """

    def test_buy_that_would_open_a_position_beyond_the_limit_is_rejected(self):
        rm = RiskManager(initial_capital=100000.0, max_positions=1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max positions" in v for v in result.violations)

    def test_short_that_would_open_a_position_beyond_the_limit_is_rejected(self):
        rm = RiskManager(initial_capital=100000.0, max_positions=1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="MSFT", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max positions" in v for v in result.violations)

    def test_buy_that_tops_up_an_open_position_is_allowed_at_the_limit(self):
        """Topping up a position that is already open does not add a position."""
        rm = RiskManager(initial_capital=100000.0, max_positions=1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_buy_that_covers_an_open_short_is_allowed_at_the_limit(self):
        """Covering a short reduces gross exposure, so it is not gated."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_positions=1,
            max_position_size=0.1,
            max_leverage=1.0,
            max_portfolio_risk=0.001,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_buy_that_opens_a_position_below_the_limit_is_allowed(self):
        rm = RiskManager(initial_capital=100000.0, max_positions=2)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_short_that_tops_up_an_open_short_is_allowed_at_the_limit(self):
        """A short is topped up to its target like a long, without adding a position."""
        rm = RiskManager(initial_capital=100000.0, max_positions=1, max_position_size=0.1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_gate_uses_the_positions_the_manager_currently_knows_about(self):
        """The gate counts ``self.positions``, refreshed by ``sync_position``."""
        rm = RiskManager(initial_capital=100000.0, max_positions=1)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max positions" in v for v in result.violations)


class TestSyncPosition:
    """Tests for sync_position."""

    def test_sync_position_adds_to_the_position_view(self):
        """A synced position becomes visible in the manager's position view."""
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        assert "AAPL" in rm.positions
        assert rm.positions["AAPL"].quantity == 100

    def test_sync_position_replaces_an_existing_position(self):
        """A synced position replaces the one the manager already held."""
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        rm.sync_position("AAPL", Position("AAPL", 200, 150.0, 150.0))
        assert rm.positions["AAPL"].quantity == 200

    def test_sync_position_none_removes_the_position(self):
        """A closed position is dropped from the position view."""
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        rm.sync_position("AAPL", None)
        assert "AAPL" not in rm.positions

    def test_sync_position_does_not_record_equity(self):
        """Syncing a position does not add a point to the equity curve."""
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        assert rm.equity_curve == [100000.0]
        assert rm.history == []

    def test_synced_position_counts_towards_the_leverage_limit(self):
        """A buy is rejected when a synced position already fills the leverage budget."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_portfolio_risk=1.0,
            max_position_size=1.0,
            max_leverage=1.0,
        )
        # The synced position already uses the whole leverage budget.
        rm.sync_position("AAPL", Position("AAPL", 500, 100.0, 100.0))
        signal = Signal(symbol="MSFT", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is False
        assert any("exceed max leverage" in v for v in result.violations)

    def test_synced_position_allows_a_sell_of_that_position(self):
        """A position opened earlier in the same cycle can be sold."""
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []


class TestShortSignals:
    """Tests for the short signal gate."""

    def test_short_within_limits(self):
        """A short inside the position limit is allowed."""
        rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_short_no_price(self):
        """A short signal without a price is rejected."""
        rm = RiskManager(initial_capital=100000.0)
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=None)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("no price" in v for v in result.violations)

    def test_short_exceeds_max_position_size(self):
        """An oversized short is rejected like an oversized long."""
        rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
        signal = Signal(symbol="AAPL", action="short", strength=2.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max position value" in v for v in result.violations)
        assert any("exceed max position size" in v for v in result.violations)

    def test_short_exceeds_portfolio_risk_budget(self):
        """A short that would push open risk above the budget is rejected."""
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
        signal = Signal(symbol="MSFT", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max portfolio risk" in v for v in result.violations)

    def test_short_exceeds_leverage_limit(self):
        """A short is measured on gross exposure, so it cannot hide behind a long."""
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
        signal = Signal(symbol="MSFT", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max leverage" in v for v in result.violations)

    def test_short_against_a_long_position_is_rejected(self):
        """A short signal does not flip an open long position."""
        rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("long holdings" in v for v in result.violations)

    def test_short_can_add_to_an_open_short(self):
        """A short is measured on the gross exposure, like a long."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_leverage=1.0,
            max_portfolio_risk=1.0,
        )
        # The open short is already above the position limit.
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("exceed max position value" in v for v in result.violations)

    def test_buy_against_an_open_short_is_allowed(self):
        """A buy covers an open short, which cannot breach a position limit."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_leverage=1.0,
            max_portfolio_risk=0.001,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is True
        assert result.violations == []

    def test_sell_against_an_open_short_is_rejected(self):
        """A sell is not a way to add to a short."""
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0),
        }
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0)
        result = rm.check_signal(signal)
        assert result.passed is False
        assert any("open short" in v for v in result.violations)


class TestTargetExposureGate:
    """The signal gate measures the exposure a position carries after the trade.

    A trade brings a position to its target, so the position size is checked
    on the target instead of on the target plus the exposure the position
    already carries, and the portfolio risk budget and the leverage limit
    are increased by the increment alone.
    """

    def test_buy_against_a_position_at_its_target_passes(self):
        """A position that already holds its full target does not block the signal."""
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_buy_against_a_position_below_its_target_passes(self):
        """A position that is part of the way to its target is not rejected.

        The signal would bring the position to its target, which is within
        the position limit, so the signal gate must not block it.
        """
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_short_against_a_position_below_its_target_passes(self):
        """A short is topped up to its target like a long."""
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="short", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_leverage_limit_is_increased_by_the_increment_only(self):
        """The leverage limit counts the exposure the trade adds, not the whole target."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_portfolio_risk=1.0,
            max_leverage=0.12,
            stop_loss_pct=0.05,
        )
        # The position carries 0.05x of the portfolio, the increment another
        # 0.05x, so the portfolio ends at 0.10x of gross exposure.
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_risk_budget_is_increased_by_the_increment_only(self):
        """The risk budget counts the risk the trade adds, not the whole target."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_portfolio_risk=0.006,
            max_leverage=10.0,
            stop_loss_pct=0.05,
        )
        # The position risks 0.25% of the portfolio, the increment another
        # 0.25%, so the portfolio ends at 0.50% of open risk.
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is True
        assert result.violations == []

    def test_a_target_above_the_position_limit_is_rejected(self):
        """A target that is above the position limit is still rejected."""
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=2.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is False
        assert any("exceed max position value" in v for v in result.violations)
        assert any("exceed max position size" in v for v in result.violations)

    def test_a_signal_above_the_risk_budget_is_rejected(self):
        """A trade that would really breach the risk budget is still rejected."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_portfolio_risk=0.004,
            max_leverage=10.0,
            stop_loss_pct=0.05,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed is False
        assert any("exceed max portfolio risk" in v for v in result.violations)

    def test_a_signal_above_the_leverage_limit_is_rejected(self):
        """A trade that would really breach the leverage limit is still rejected."""
        rm = RiskManager(
            initial_capital=100000.0,
            max_position_size=0.1,
            max_portfolio_risk=1.0,
            max_leverage=0.08,
            stop_loss_pct=0.05,
        )
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=100.0, current_price=100.0),
        }
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
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

    def test_is_short_position(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=160),
            "MSFT": Position(symbol="MSFT", quantity=-100, avg_price=150, current_price=160),
            "FLAT": Position(symbol="FLAT", quantity=0, avg_price=150, current_price=160),
        }
        assert rm.is_short_position("MSFT") is True
        assert rm.is_short_position("AAPL") is False
        assert rm.is_short_position("FLAT") is False
        assert rm.is_short_position("UNKNOWN") is False

    def test_get_position_stop_loss_short(self):
        """A short's stop loss sits above its entry price."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150, current_price=160)
        }
        assert rm.get_position_stop_loss("AAPL") == 150 * 1.1

    def test_should_stop_loss_short_triggered(self):
        """A short stops out when the price rises to the stop level."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150, current_price=160)
        }
        assert rm.should_stop_loss("AAPL", 170.0) is True
        assert rm.should_stop_loss("AAPL", 165.0) is True
        assert rm.should_stop_loss("AAPL", 160.0) is False
        assert rm.should_stop_loss("AAPL", 100.0) is False
        assert rm.should_stop_loss("UNKNOWN", 100.0) is False

    def test_get_position_take_profit_short(self):
        """A short's take profit sits below its entry price."""
        rm = RiskManager(initial_capital=100000.0, take_profit_pct=0.15)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150, current_price=160)
        }
        assert rm.get_position_take_profit("AAPL") == 150 * 0.85

    def test_should_take_profit_short_triggered(self):
        """A short takes profit when the price falls to the target level."""
        rm = RiskManager(initial_capital=100000.0, take_profit_pct=0.15)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150, current_price=160)
        }
        assert rm.should_take_profit("AAPL", 120.0) is True
        assert rm.should_take_profit("AAPL", 127.5) is True
        assert rm.should_take_profit("AAPL", 130.0) is False
        assert rm.should_take_profit("AAPL", 200.0) is False
        assert rm.should_take_profit("UNKNOWN", 200.0) is False

    def test_short_stop_loss_and_take_profit_do_not_overlap(self):
        """A short's stop is above its target, so the two levels are distinct."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10, take_profit_pct=0.15)
        rm.positions = {
            "AAPL": Position(symbol="AAPL", quantity=-100, avg_price=150, current_price=150)
        }
        stop = rm.get_position_stop_loss("AAPL")
        target = rm.get_position_take_profit("AAPL")
        assert stop is not None and target is not None
        assert stop > target

    def test_short_thresholds_use_the_mirrored_direction(self):
        """The mirrored levels are exactly the mirror image of the long ones."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10, take_profit_pct=0.15)
        rm.positions = {
            "LONG": Position(symbol="LONG", quantity=100, avg_price=150, current_price=150),
            "SHORT": Position(symbol="SHORT", quantity=-100, avg_price=150, current_price=150),
        }
        long_stop = rm.get_position_stop_loss("LONG")
        short_stop = rm.get_position_stop_loss("SHORT")
        long_target = rm.get_position_take_profit("LONG")
        short_target = rm.get_position_take_profit("SHORT")
        assert long_stop is not None and short_stop is not None
        assert long_target is not None and short_target is not None
        assert long_stop + short_stop == pytest.approx(300.0)
        assert long_target + short_target == pytest.approx(300.0)

    def test_short_thresholds_follow_a_synchronized_short_position(self):
        """The helpers read the manager's position view, as the signal gate does."""
        rm = RiskManager(initial_capital=100000.0, stop_loss_pct=0.10, take_profit_pct=0.15)
        rm.sync_position("AAPL", Position("AAPL", -100, 150.0, 150.0))
        assert rm.get_position_stop_loss("AAPL") == 150 * 1.1
        assert rm.get_position_take_profit("AAPL") == 150 * 0.85
        assert rm.should_stop_loss("AAPL", 160.0) is False
        assert rm.should_take_profit("AAPL", 140.0) is False


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


class TestTrailingStop:
    """Tests for trailing stops."""

    def test_trailing_stop_is_disabled_by_default(self):
        rm = RiskManager(initial_capital=100000.0)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        assert rm.get_trailing_stop("AAPL") is None
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(95.0)

    def test_long_trailing_stop_follows_the_highest_price(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(114.0)
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(114.0)

    def test_long_trailing_stop_never_loosens(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        rm.update_trailing_stop("AAPL", 110.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(114.0)
        assert rm.should_stop_loss("AAPL", 113.0) is True
        assert rm.should_stop_loss("AAPL", 115.0) is False

    def test_short_trailing_stop_follows_the_lowest_price(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 80.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(84.0)
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(84.0)

    def test_short_trailing_stop_never_loosens(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 80.0)
        rm.update_trailing_stop("AAPL", 90.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(84.0)
        assert rm.should_stop_loss("AAPL", 85.0) is True
        assert rm.should_stop_loss("AAPL", 83.0) is False

    def test_fixed_stop_is_used_until_the_trailing_stop_is_tighter(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.10, stop_loss_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 100.0)
        # 100 * 0.90 = 90.0 is looser than the fixed 95.0 stop.
        assert rm.get_trailing_stop("AAPL") == pytest.approx(90.0)
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(95.0)
        rm.update_trailing_stop("AAPL", 110.0)
        # 110 * 0.90 = 99.0 is tighter than the fixed 95.0 stop.
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(99.0)

    def test_short_fixed_stop_is_used_until_the_trailing_stop_is_tighter(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.10, stop_loss_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 100.0)
        # 100 * 1.10 = 110.0 is looser than the fixed 105.0 stop.
        assert rm.get_trailing_stop("AAPL") == pytest.approx(110.0)
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(105.0)
        rm.update_trailing_stop("AAPL", 90.0)
        # 90 * 1.10 = 99.0 is tighter than the fixed 105.0 stop.
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(99.0)

    def test_trailing_stop_waits_for_the_activation_threshold(self):
        rm = RiskManager(
            initial_capital=100000.0,
            trailing_stop_pct=0.05,
            trailing_stop_activation_pct=0.10,
        )
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 105.0)
        assert rm.get_trailing_stop("AAPL") is None
        assert rm.get_position_stop_loss("AAPL") == pytest.approx(95.0)
        rm.update_trailing_stop("AAPL", 111.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(105.45)

    def test_short_trailing_stop_waits_for_the_activation_threshold(self):
        rm = RiskManager(
            initial_capital=100000.0,
            trailing_stop_pct=0.05,
            trailing_stop_activation_pct=0.10,
        )
        rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 95.0)
        assert rm.get_trailing_stop("AAPL") is None
        rm.update_trailing_stop("AAPL", 89.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(93.45)

    def test_portfolio_update_feeds_the_price_to_the_tracker(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        positions = {"AAPL": Position("AAPL", 100, 100.0, 120.0)}
        rm.update_portfolio_value(positions, 50000.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(114.0)

    def test_closing_a_position_clears_the_trailing_stop(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        assert rm.get_trailing_stop("AAPL") is not None
        rm.sync_position("AAPL", None)
        assert rm.get_trailing_stop("AAPL") is None

    def test_a_dropped_position_clears_the_trailing_stop(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        positions = {"AAPL": Position("AAPL", 100, 100.0, 120.0)}
        rm.update_portfolio_value(positions, 50000.0)
        assert rm.get_trailing_stop("AAPL") is not None
        rm.update_portfolio_value({}, 50000.0)
        assert rm.get_trailing_stop("AAPL") is None

    def test_flipping_the_direction_clears_the_trailing_stop(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        rm.sync_position("AAPL", Position("AAPL", -100, 120.0, 120.0))
        # The long stop (114.0) does not carry over to the short.
        assert rm.get_trailing_stop("AAPL") == pytest.approx(126.0)

    def test_reset_clears_the_trailing_stop(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
        rm.update_trailing_stop("AAPL", 120.0)
        rm.reset()
        assert rm.get_trailing_stop("AAPL") is None

    def test_trailing_stop_ignores_symbols_without_a_position(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        assert rm.update_trailing_stop("AAPL", 120.0) is None
        assert rm.get_trailing_stop("AAPL") is None

    def test_trailing_stop_ignores_non_positive_prices(self):
        rm = RiskManager(initial_capital=100000.0, trailing_stop_pct=0.05)
        rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 0.0))
        rm.update_trailing_stop("AAPL", 0.0)
        assert rm.get_trailing_stop("AAPL") is None
        rm.update_trailing_stop("AAPL", 120.0)
        assert rm.get_trailing_stop("AAPL") == pytest.approx(114.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
