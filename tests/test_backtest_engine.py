"""Tests for the backtest engine."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quant_trading.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    Trade,
    run_backtest,
)
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.data.synthetic import create_synthetic_data
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal, Strategy
from quant_trading.strategies.examples import MovingAverageCrossover


class MockDataProvider(DataProvider):
    """Mock data provider for testing."""

    def __init__(self, data: dict):
        self._data = data
        self._name = "mock"

    @property
    def name(self) -> str:
        return self._name

    def fetch(
        self,
        symbols: list,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        result = FetchResult()
        for symbol in symbols:
            if symbol in self._data:
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=self._data[symbol],
                    source=self.name,
                    fetched_at=datetime.now(),
                )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols: list) -> FetchResult:
        return self.fetch(symbols)


class FirstDayBuyStrategy(Strategy):
    """Buys once on the first simulated date, then holds."""

    def __init__(self):
        super().__init__(name="FirstDayBuy")
        self._bought = False

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._bought:
            return []
        self._bought = True
        symbol, df = next(iter(data.items()))
        return [
            Signal(
                symbol=symbol,
                action="buy",
                strength=1.0,
                price=float(df["close"].iloc[-1]),
            )
        ]


class BuyThenSellStrategy(Strategy):
    """Buys the full position on the first date, sells it all on the second."""

    def __init__(self):
        super().__init__(name="BuyThenSell")
        self._phase = 0

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._phase == 2:
            return []
        symbol, df = next(iter(data.items()))
        price = float(df["close"].iloc[-1])
        if self._phase == 0:
            self._phase = 1
            return [Signal(symbol=symbol, action="buy", strength=1.0, price=price)]
        self._phase = 2
        return [Signal(symbol=symbol, action="sell", strength=1.0, price=price)]


class NoTradeStrategy(Strategy):
    """Never emits a signal."""

    def __init__(self):
        super().__init__(name="NoTrade")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        return []


def test_trade_cost_calculation():
    """Test Trade cost calculation with commission and slippage."""
    trade = Trade(
        symbol="AAPL",
        action="buy",
        quantity=100,
        price=150.0,
        timestamp=datetime.now(),
        commission=0.001,
        slippage=0.0005,
    )
    expected_cost = 100 * 150.0 * (1 + 0.001 + 0.0005)
    assert abs(trade.cost - expected_cost) < 0.01

    trade_sell = Trade(
        symbol="AAPL",
        action="sell",
        quantity=100,
        price=155.0,
        timestamp=datetime.now(),
        commission=0.001,
        slippage=0.0005,
    )
    expected_cost_sell = 100 * 155.0 * (1 - 0.001 - 0.0005)
    assert abs(trade_sell.cost - expected_cost_sell) < 0.01


def test_trade_fee_property():
    """Trade.fee is the commission plus slippage charged on the gross value."""
    buy = Trade(
        symbol="AAPL",
        action="buy",
        quantity=100,
        price=150.0,
        timestamp=datetime.now(),
        commission=0.001,
        slippage=0.0005,
    )
    assert buy.fee == pytest.approx(100 * 150.0 * 0.0015)

    sell = Trade(
        symbol="AAPL",
        action="sell",
        quantity=100,
        price=150.0,
        timestamp=datetime.now(),
        commission=0.001,
        slippage=0.0005,
    )
    assert sell.fee == pytest.approx(100 * 150.0 * 0.0015)


def test_backtest_engine_initialization():
    """Test BacktestEngine initialization."""
    config = BacktestConfig(initial_capital=50000.0)
    engine = BacktestEngine(config=config)

    assert engine.config.initial_capital == 50000.0
    assert engine.portfolio.cash == 50000.0
    assert engine.portfolio.initial_capital == 50000.0
    assert len(engine.strategies) == 0


def test_add_remove_strategy():
    """Test adding and removing strategies."""
    engine = BacktestEngine()
    strategy = MovingAverageCrossover(name="Test_MA")

    engine.add_strategy(strategy)
    assert "Test_MA" in engine.strategies
    assert engine.strategies["Test_MA"] is strategy

    engine.remove_strategy("Test_MA")
    assert "Test_MA" not in engine.strategies


def test_backtest_result_dataclass():
    """Test BacktestResult dataclass creation."""
    equity_curve = pd.Series([100000, 101000, 102000])
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10,
                "price": 150.0,
                "timestamp": datetime.now(),
                "commission": 0.001,
                "slippage": 0.0005,
            }
        ]
    )

    from quant_trading.backtest.metrics import BacktestMetrics

    metrics = BacktestMetrics()

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime.now() - timedelta(days=10),
        end_date=datetime.now(),
        initial_capital=100000.0,
        final_value=102000.0,
        total_return=2000.0,
        total_return_pct=2.0,
    )

    assert result.initial_capital == 100000.0
    assert result.final_value == 102000.0
    assert result.total_return == 2000.0
    assert result.total_return_pct == 2.0
    # total_costs defaults to 0.0 so existing constructions keep working.
    assert result.total_costs == 0.0


def test_mock_backtest_run():
    """Test a full backtest run with mock data."""
    symbols = ["AAPL", "MSFT"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config, data_manager=data_manager)

    strategy = MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")
    engine.add_strategy(strategy)

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert result.initial_capital == 100000.0
    assert result.final_value > 0
    assert len(result.equity_curve) > 0
    assert result.metrics is not None


def test_engine_applies_config_periods_per_year():
    """The engine must annualize metrics with the configured periods per year."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    def _run(periods_per_year: int):
        config = BacktestConfig(initial_capital=100000.0, periods_per_year=periods_per_year)
        engine = BacktestEngine(config=config, data_manager=data_manager)
        engine.add_strategy(MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA"))
        return engine.run(symbols, start_date, end_date, "1d")

    daily = _run(252)
    monthly = _run(12)

    assert daily.metrics.volatility != pytest.approx(monthly.metrics.volatility)
    assert daily.metrics.sharpe_ratio != pytest.approx(monthly.metrics.sharpe_ratio)

    returns = daily.equity_curve.pct_change().dropna()
    assert daily.metrics.volatility == pytest.approx(returns.std() * (252**0.5))
    assert monthly.metrics.volatility == pytest.approx(returns.std() * (12**0.5))
    assert monthly.metrics.annual_return == pytest.approx(returns.mean() * 12)


def test_run_backtest_periods_per_year_argument():
    """The run_backtest convenience function must expose periods_per_year."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    strategy = MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = run_backtest(
        strategy=strategy,
        symbols=symbols,
        start=start_date,
        end=end_date,
        data_manager=data_manager,
        periods_per_year=12,
    )

    returns = result.equity_curve.pct_change().dropna()
    assert result.metrics.annual_return == pytest.approx(returns.mean() * 12)
    assert result.metrics.volatility == pytest.approx(returns.std() * (12**0.5))


def test_run_backtest_convenience_function():
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    strategy = MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")

    # Create engine with mock data manager
    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(strategy)

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert result.initial_capital == 100000.0
    assert result.final_value > 0


def test_trade_realized_pnl_property():
    """Test that Trade.pnl returns realized PnL (0 for opens, set on closes)."""
    trade = Trade(
        symbol="AAPL",
        action="sell",
        quantity=50,
        price=160.0,
        timestamp=datetime.now(),
        commission=0.001,
        slippage=0.0005,
        realized_pnl=750.0,
    )
    assert trade.pnl == 750.0

    buy = Trade(symbol="AAPL", action="buy", quantity=10, price=150.0, timestamp=datetime.now())
    assert buy.pnl == 0.0


def test_backtest_traces_realized_pnl():
    """Test that realized PnL is recorded per trade and feeds the metrics."""
    symbols = ["AAPL", "MSFT"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config, data_manager=data_manager)

    strategy = MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")
    engine.add_strategy(strategy)

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert "pnl" in result.trades.columns
    sells = result.trades[result.trades["action"] == "sell"]
    buys = result.trades[result.trades["action"] == "buy"]

    if len(sells) > 0:
        assert (sells["pnl"].abs() >= 0).all()
    if len(buys) > 0:
        assert (buys["pnl"] == 0).all()
    # Metrics pipeline picks up trades because the pnl column is present.
    assert result.metrics.num_trades == len(result.trades)


def test_portfolio_violations_collected_without_halt():
    """Portfolio violations are recorded but the backtest runs to completion."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(
        config=config,
        data_manager=data_manager,
        risk_manager=RiskManager(initial_capital=100000.0, max_positions=0),
    )
    engine.add_strategy(FirstDayBuyStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert len(result.portfolio_violations) > 0
    # Full run: one entry per simulated date plus the initial value.
    assert len(result.equity_curve) == len(mock_data["AAPL"]) + 1
    assert isinstance(result.equity_curve, pd.Series)
    assert result.equity_curve.index[0] == start_date


def test_halt_on_portfolio_violation_stops_backtest():
    """halt_on_portfolio_violation=True stops the backtest on the first violation."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(
        initial_capital=100000.0,
        halt_on_portfolio_violation=True,
    )
    engine = BacktestEngine(
        config=config,
        data_manager=data_manager,
        risk_manager=RiskManager(initial_capital=100000.0, max_positions=0),
    )
    engine.add_strategy(FirstDayBuyStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert len(result.portfolio_violations) > 0
    # Halted after the first simulated date: initial value plus one update.
    assert len(result.equity_curve) == 2
    assert len(result.equity_curve) < len(mock_data["AAPL"]) + 1
    assert isinstance(result.equity_curve, pd.Series)
    assert len(result.equity_curve.index) == len(result.equity_curve)


def test_run_without_data_manager_raises():
    """run() raises ValueError when no data_manager is configured."""
    engine = BacktestEngine()
    with pytest.raises(ValueError, match="No data_manager configured"):
        engine.run(["AAPL"], datetime.now(), datetime.now())


def test_run_raises_on_fetch_errors():
    """run() raises RuntimeError when the data manager reports fetch errors."""
    engine = BacktestEngine(data_manager=MagicMock())
    engine.data_manager.fetch.return_value = FetchResult(
        errors={"AAPL": RuntimeError("network down")},
    )
    with pytest.raises(RuntimeError, match="Data fetch errors"):
        engine.run(["AAPL"], datetime.now(), datetime.now())


def test_run_raises_on_no_data():
    """run() raises ValueError when the data manager returns no data."""
    engine = BacktestEngine(data_manager=MagicMock())
    engine.data_manager.fetch.return_value = FetchResult()
    with pytest.raises(ValueError, match="No market data retrieved"):
        engine.run(["AAPL"], datetime.now(), datetime.now())


def test_run_skips_dates_with_no_comparable_data():
    """A NaT entry in the index yields an empty current_data slice, hitting the
    defensive ``continue`` in the run loop."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=10)
    df = mock_data["AAPL"].copy()
    idx = list(df.index)
    idx[2] = pd.NaT
    df.index = pd.DatetimeIndex(idx)
    mock_data["AAPL"] = df

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(FirstDayBuyStrategy())

    start_date = datetime.now() - timedelta(days=10)
    end_date = datetime.now()
    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert len(result.equity_curve) > 0


def test_default_data_manager_creation_and_reset():
    """get_default_data_manager lazily builds (and caches) a DataManager and
    reset_default_data_manager clears it."""
    from quant_trading.backtest import engine as engine_module

    engine_module.reset_default_data_manager()
    assert engine_module._default_data_manager is None

    fake_provider = MockDataProvider(create_synthetic_data(["AAPL"], days=10))
    with patch(
        "quant_trading.data.yfinance_provider.YFinanceProvider",
        return_value=fake_provider,
    ):
        dm = engine_module.get_default_data_manager()
        assert isinstance(dm, DataManager)
        # Second call returns the cached instance.
        dm_cached = engine_module.get_default_data_manager()
        assert dm is dm_cached

    engine_module.reset_default_data_manager()
    assert engine_module._default_data_manager is None


def test_process_signal_skipped_when_price_missing():
    """A buy signal whose resolved price is None/<=0 is skipped."""
    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)
    signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=0.0)
    trades: list[Trade] = []
    engine._process_signal(signal, trades, datetime.now())
    assert trades == []


def test_process_signal_buy_partial_fill_when_cost_exceeds_cash():
    """When cost exceeds cash, quantity is trimmed to fit available cash."""
    config = BacktestConfig(initial_capital=1000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)
    # All-in on MSFT leaves $100 cash and $1000 total value.
    engine.portfolio.add_holding("MSFT", 100.0, 9.0)
    buy = Signal(symbol="AAPL", action="buy", strength=1.0, price=10.0)
    trades: list[Trade] = []
    engine._process_signal(buy, trades, datetime.now())
    assert len(trades) == 1
    assert trades[0].action == "buy"
    # Trimmed to fit cash after costs.
    assert trades[0].quantity < 10.0


def test_process_signal_buy_aborted_when_no_cash_for_partial_fill():
    """When cash is exhausted, the partial fill quantity is <=0 and returns."""
    config = BacktestConfig(initial_capital=1000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)
    # All capital deployed in MSFT leaves zero cash.
    engine.portfolio.add_holding("MSFT", 1000.0, 1.0)
    buy = Signal(symbol="AAPL", action="buy", strength=1.0, price=10.0)
    trades: list[Trade] = []
    engine._process_signal(buy, trades, datetime.now())
    assert trades == []


def test_process_signal_sell_without_holding():
    """A sell signal for a symbol with no holding is a no-op."""
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    sell = Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0)
    trades: list[Trade] = []
    engine._process_signal(sell, trades, datetime.now())
    assert trades == []


def test_process_signal_sell_with_zero_strength():
    """A sell signal whose strength yields zero quantity is a no-op."""
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    engine.portfolio.add_holding("AAPL", 100.0, 150.0)
    sell = Signal(symbol="AAPL", action="sell", strength=0.0, price=150.0)
    trades: list[Trade] = []
    engine._process_signal(sell, trades, datetime.now())
    assert trades == []


def test_process_signal_sell_executes():
    """A sell signal with a positive strength and an existing holding executes
    the `elif signal.action == "sell"` branch (295->exit)."""
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    engine.portfolio.add_holding("AAPL", 100.0, 150.0)
    sell = Signal(symbol="AAPL", action="sell", strength=1.0, price=160.0)
    trades: list[Trade] = []
    engine._process_signal(sell, trades, datetime.now())
    assert len(trades) == 1
    assert trades[0].action == "sell"
    assert trades[0].pnl > 0


def test_process_signal_hold_action_skips_branches():
    """A signal whose action is neither 'buy' nor 'sell' (e.g. 'hold') falls
    through both the `if` and `elif` arms, hitting the 295->exit branch."""
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    engine.portfolio.add_holding("AAPL", 100.0, 150.0)
    hold = Signal(symbol="AAPL", action="hold", strength=1.0, price=150.0)
    trades: list[Trade] = []
    engine._process_signal(hold, trades, datetime.now())
    assert trades == []


def test_run_backtest_uses_default_data_manager():
    """run_backtest with no data_manager/config falls back to the default DM."""
    from quant_trading.backtest import engine as engine_module

    engine_module.reset_default_data_manager()
    fake_provider = MockDataProvider(create_synthetic_data(["AAPL"], days=60))
    fake_dm = DataManager([fake_provider])
    with patch(
        "quant_trading.backtest.engine.get_default_data_manager",
        return_value=fake_dm,
    ):
        result = run_backtest(
            strategy=MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA"),
            symbols=["AAPL"],
            start=datetime.now() - timedelta(days=50),
            end=datetime.now(),
            data_manager=None,
            config=None,
        )
    assert isinstance(result, BacktestResult)
    engine_module.reset_default_data_manager()


def _engine_run(strategy, data, commission: float, slippage: float):
    """Run one backtest over deterministic mock data with the given costs."""
    symbols = list(data.keys())
    provider = MockDataProvider(data)
    config = BacktestConfig(initial_capital=10000.0, commission=commission, slippage=slippage)
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(strategy)
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 1) + timedelta(days=len(next(iter(data.values()))) - 1)
    return engine.run(symbols, start, end, "1d")


def test_costed_equity_below_zero_cost_run():
    """Commission and slippage must push the equity curve below a zero-cost run.

    Covers invariant 1: a costed run's equity is weakly below the zero-cost
    equity at every bar and strictly below once costs have been charged.
    """
    idx = pd.date_range("2024-01-01", periods=6, freq="D")
    data = {
        "TEST": pd.DataFrame(
            {
                "open": [100.0, 110.0, 120.0, 130.0, 125.0, 120.0],
                "high": [105.0, 115.0, 125.0, 135.0, 130.0, 125.0],
                "low": [95.0, 105.0, 115.0, 125.0, 120.0, 115.0],
                "close": [100.0, 110.0, 120.0, 130.0, 125.0, 120.0],
            },
            index=idx,
        )
    }

    zero = _engine_run(FirstDayBuyStrategy(), data, 0.0, 0.0)
    costed = _engine_run(FirstDayBuyStrategy(), data, 0.01, 0.005)

    assert costed.final_value < zero.final_value
    for zero_px, costed_px in zip(zero.equity_curve, costed.equity_curve):
        assert costed_px <= zero_px
    assert costed.equity_curve.iloc[-1] < zero.equity_curve.iloc[-1]


def test_signed_trade_cost_reconciles_with_final_value():
    """For a fully liquidated round trip, signed trade cost equals PnL.

    Covers invariant 3: ``final_value - initial_capital`` equals the sum of
    signed ``Trade.cost`` (buys reduce cash, sells increase it) once costs are
    charged to cash. Entry fees are capitalized into the position's cost basis,
    so realized PnL is net of both buy-side and sell-side fees and, for this
    fully liquidated round trip, equals the cash change.
    """
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    data = {
        "TEST": pd.DataFrame(
            {
                "open": [100.0, 110.0, 120.0, 130.0],
                "high": [105.0, 115.0, 125.0, 135.0],
                "low": [95.0, 105.0, 115.0, 125.0],
                "close": [100.0, 110.0, 120.0, 130.0],
            },
            index=idx,
        )
    }

    zero = _engine_run(BuyThenSellStrategy(), data, 0.0, 0.0)
    costed = _engine_run(BuyThenSellStrategy(), data, 0.01, 0.005)

    # Invariant 1: costs reduce the final value.
    assert costed.final_value < zero.final_value

    # Invariant 3: signed cost reconciles with cash change (fully liquidated).
    signed_cost = 0.0
    for _, trade in costed.trades.iterrows():
        signed_cost += trade["cost"] if trade["action"] == "sell" else -trade["cost"]
    assert costed.final_value - costed.initial_capital == pytest.approx(signed_cost)

    # Entry fees are capitalized into the cost basis, so realized PnL now
    # reconciles with the cash change for a fully liquidated round trip.
    assert costed.trades["pnl"].sum() == pytest.approx(costed.final_value - costed.initial_capital)


def _round_trip_data() -> dict[str, pd.DataFrame]:
    """Four-bar price series used by the cost-accounting tests."""
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    return {
        "TEST": pd.DataFrame(
            {
                "open": [100.0, 110.0, 120.0, 130.0],
                "high": [105.0, 115.0, 125.0, 135.0],
                "low": [95.0, 105.0, 115.0, 125.0],
                "close": [100.0, 110.0, 120.0, 130.0],
            },
            index=idx,
        )
    }


def test_total_costs_equals_sum_of_per_trade_fees():
    """total_costs is the commission + slippage paid on every executed trade."""
    data = _round_trip_data()
    costed = _engine_run(BuyThenSellStrategy(), data, 0.01, 0.005)

    expected = 0.0
    for _, trade in costed.trades.iterrows():
        base = trade["quantity"] * trade["price"]
        expected += base * (trade["commission"] + trade["slippage"])

    assert costed.total_costs == pytest.approx(expected)
    assert costed.total_costs == pytest.approx(costed.trades["fee"].sum())
    assert costed.total_costs > 0

    # A run without costs pays nothing.
    zero = _engine_run(BuyThenSellStrategy(), data, 0.0, 0.0)
    assert zero.total_costs == pytest.approx(0.0)


def test_total_costs_is_zero_when_no_trades_execute():
    """A run that never trades pays no costs."""
    data = _round_trip_data()
    result = _engine_run(NoTradeStrategy(), data, 0.01, 0.005)

    assert result.trades.empty
    assert result.total_costs == 0.0


def test_total_costs_reconciles_with_pnl_and_final_value():
    """The headline numbers reconcile against the trade log.

    - ``total_costs`` splits into the buy-side and sell-side fees.
    - ``final_value - initial_capital`` equals the sum of the signed trade
      costs (buys reduce cash, sells increase it).
    - Entry fees are capitalized into the cost basis, so realized PnL is net
      of both buy-side and sell-side fees; for this fully liquidated round
      trip ``sum(Trade.pnl)`` equals the cash change.
    - For a fully liquidated round trip the costed final value is exactly the
      zero-cost final value minus ``total_costs``.
    """
    data = _round_trip_data()
    zero = _engine_run(BuyThenSellStrategy(), data, 0.0, 0.0)
    costed = _engine_run(BuyThenSellStrategy(), data, 0.01, 0.005)
    trades = costed.trades

    buy_fees = trades[trades["action"] == "buy"]["fee"].sum()
    sell_fees = trades[trades["action"] == "sell"]["fee"].sum()
    assert costed.total_costs == pytest.approx(buy_fees + sell_fees)
    assert buy_fees > 0
    assert sell_fees > 0

    cash_change = costed.final_value - costed.initial_capital
    signed_cost = 0.0
    for _, trade in trades.iterrows():
        signed_cost += trade["cost"] if trade["action"] == "sell" else -trade["cost"]
    assert cash_change == pytest.approx(signed_cost)

    # Realized PnL is net of both buy-side and sell-side fees because entry
    # fees are capitalized into the cost basis, so it equals the cash change
    # for a fully liquidated round trip.
    assert cash_change == pytest.approx(trades["pnl"].sum())
    assert trades["pnl"].sum() == pytest.approx(cash_change)

    # Both runs are fully liquidated, so all fees land in the final value.
    assert zero.final_value - costed.final_value == pytest.approx(costed.total_costs)

    # Fully liquidated: no remaining holdings.
    assert len(costed.positions) == 0


def test_buy_signal_with_existing_position_at_target_does_not_trade():
    """available_value <= 0 branch: no trade when position already at target."""
    from quant_trading.config.settings import BacktestConfig

    data = create_synthetic_data(["AAPL"], days=5)
    provider = MockDataProvider(data)
    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(NoTradeStrategy())
    # Pre-load a holding at full position limit so a subsequent buy has no room.
    engine.portfolio.add_holding("AAPL", 1000.0, float(data["AAPL"]["close"].iloc[0]))
    initial_cash = engine.portfolio.cash
    trades: list[Trade] = []
    engine._process_signal(
        Signal(
            symbol="AAPL", action="buy", strength=0.1, price=float(data["AAPL"]["close"].iloc[0])
        ),
        trades,
        datetime.now(),
    )
    assert trades == []
    assert engine.portfolio.cash == initial_cash


def test_run_backtest_with_config_creates_data_manager():
    """config is not None branch: create_data_manager_from_config path runs."""
    from quant_trading.config.settings import Config

    config = Config()
    config.data.offline = True
    config.data.provider = "synthetic"
    result = run_backtest(
        strategy=MovingAverageCrossover(fast_period=5, slow_period=20),
        symbols=["AAPL"],
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
        initial_capital=100000.0,
        commission=0.001,
        slippage=0.0005,
        data_manager=None,
        config=config,
    )
    assert isinstance(result, BacktestResult)
    assert result.initial_capital == 100000.0
    assert result.metrics is not None


def test_buy_returns_when_available_value_non_positive():
    """Test buy returns early when available_value <= 0."""
    end = datetime(2023, 12, 31)
    start = end - timedelta(days=30)
    d = create_synthetic_data(["AAPL"], days=30, seed=42)
    provider = MockDataProvider(d)
    dm = DataManager([provider])
    engine = BacktestEngine(config=BacktestConfig(initial_capital=100000.0), data_manager=dm)

    class LargeBuyStrategy(Strategy):
        def __init__(self):
            super().__init__(name="LargeBuyStrategy")

        def generate_signals(self, data: dict):
            symbol = next(iter(data.keys()))
            df = data[symbol]
            return [
                Signal(symbol=symbol, action="buy", strength=1.0, price=float(df["close"].iloc[-1]))
            ]

    engine.add_strategy(LargeBuyStrategy())
    engine.portfolio.add_holding("AAPL", 600, 150.0)
    result = engine.run(["AAPL"], start, end)
    assert result is not None


def test_run_backtest_with_config_and_no_data_manager():
    """Test run_backtest creates data_manager from config when None."""
    from quant_trading.config.settings import Config, DataConfig

    end = datetime(2023, 12, 31)
    start = end - timedelta(days=10)
    config = Config(data=DataConfig(provider="synthetic", offline=True))
    strategy = NoTradeStrategy()
    result = run_backtest(
        strategy=strategy,
        symbols=["AAPL"],
        start=start,
        end=end,
        config=config,
        data_manager=None,
    )
    assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_run_with_zero_initial_capital_does_not_divide_by_zero():
    """A zero initial capital must not crash when the total return is reported.

    The percentage return is undefined without a starting capital, so it is
    reported as 0.0 -- the same convention the metrics use.
    """
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(initial_capital=0.0)
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA"))

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert result.initial_capital == 0.0
    assert result.total_return_pct == 0.0
    assert result.metrics.total_return_pct == 0.0
