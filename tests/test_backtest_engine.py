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
from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)
from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.data.synthetic import create_synthetic_data
from quant_trading.portfolio.portfolio import Holding
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


class BuyAllSymbolsStrategy(Strategy):
    """Buys every symbol on the first simulated date, all in the same bar."""

    def __init__(self):
        super().__init__(name="BuyAllSymbols")
        self._bought = False

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._bought:
            return []
        self._bought = True
        return [
            Signal(
                symbol=symbol,
                action="buy",
                strength=1.0,
                price=float(df["close"].iloc[-1]),
            )
            for symbol, df in data.items()
        ]


class BuyThenSellSameBarStrategy(Strategy):
    """Buys and then sells the same symbol inside a single bar."""

    def __init__(self):
        super().__init__(name="BuyThenSellSameBar")
        self._done = False

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._done:
            return []
        self._done = True
        symbol, df = next(iter(data.items()))
        price = float(df["close"].iloc[-1])
        return [
            Signal(symbol=symbol, action="buy", strength=1.0, price=price),
            Signal(symbol=symbol, action="sell", strength=1.0, price=price),
        ]


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
    """Portfolio violations are recorded but the backtest runs to completion.

    The violation is forced with a ``max_drawdown`` that the fee paid on the
    first bar breaches: the portfolio marks below its initial capital on the
    bar the position is opened, so the drawdown limit is exceeded. The
    position-size limit is breached too, because the fee shrinks the portfolio
    value just below the size of the position. ``max_positions`` is left at
    its default so the signal gate does not reject the entry.
    """
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(
        config=config,
        data_manager=data_manager,
        risk_manager=RiskManager(initial_capital=100000.0, max_drawdown=0.0001),
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
    """halt_on_portfolio_violation=True stops the backtest on the first violation.

    The violation is forced with a ``max_drawdown`` that the fee paid on the
    first bar breaches: the portfolio marks below its initial capital on the
    bar the position is opened, so the drawdown limit is exceeded. The
    position-size limit is breached too, because the fee shrinks the portfolio
    value just below the size of the position. ``max_positions`` is left at
    its default so the signal gate does not reject the entry.
    """
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
        risk_manager=RiskManager(initial_capital=100000.0, max_drawdown=0.0001),
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


def test_config_driven_max_drawdown_halts_backtest():
    """A config-driven ``max_drawdown`` halts a multi-symbol backtest.

    The violation is forced with a ``max_drawdown`` that the fee paid on the
    first bar breaches: the portfolio marks below its initial capital on the
    bar the position is opened, so the drawdown limit is exceeded. The
    position-size limit is breached too, because the fee shrinks the portfolio
    value just below the size of the position. ``max_positions`` is left at
    its default so the signal gate does not reject the entry.
    """
    symbols = ["AAPL", "MSFT"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = Config(
        backtest=BacktestConfig(
            initial_capital=100000.0,
            halt_on_portfolio_violation=True,
        ),
        risk=RiskConfig(max_drawdown=0.0001),
    )
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(FirstDayBuyStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert len(result.portfolio_violations) > 0
    assert len(result.equity_curve) < len(mock_data["AAPL"]) + 1


def test_portfolio_at_its_position_limit_does_not_open_a_new_position():
    """A portfolio at ``max_positions`` does not open a new position.

    With ``max_positions=1`` the first bar opens AAPL and the MSFT buy is
    rejected by the signal gate, so the backtest ends with one position and
    one trade instead of two.
    """
    symbols = ["AAPL", "MSFT"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = Config(
        backtest=BacktestConfig(initial_capital=100000.0),
        portfolio=PortfolioConfig(max_positions=1),
    )
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(BuyAllSymbolsStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert len(result.trades) == 1
    assert set(result.positions) == {"AAPL"}


def test_same_bar_buys_are_measured_against_the_exposure_they_add():
    """A second buy in the same bar is rejected when it breaks the leverage limit."""
    symbols = ["AAPL", "MSFT"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    config = Config(
        backtest=BacktestConfig(initial_capital=100000.0),
        risk=RiskConfig(
            max_position_size=0.5,
            max_portfolio_risk=1.0,
            max_leverage=0.5,
        ),
    )
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(BuyAllSymbolsStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    # The first buy uses the whole leverage budget, so the second one is rejected.
    assert len(result.trades) == 1
    assert list(result.positions) == ["AAPL"]
    gross = sum(abs(p.market_value) for p in result.positions.values())
    assert gross / result.final_value <= 0.5


def test_position_opened_in_the_same_bar_can_be_sold_again():
    """A sell in the same bar as its buy is executed instead of being rejected."""
    symbols = ["AAPL"]
    mock_data = create_synthetic_data(symbols, days=60)

    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    engine = BacktestEngine(
        config=BacktestConfig(initial_capital=100000.0),
        data_manager=data_manager,
    )
    engine.add_strategy(BuyThenSellSameBarStrategy())

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()

    result = engine.run(symbols, start_date, end_date, "1d")

    assert isinstance(result, BacktestResult)
    assert list(result.trades["action"]) == ["buy", "sell"]
    # The round trip closed the position again.
    assert result.positions == {}


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


# ---------------------------------------------------------------------------
# Short selling
# ---------------------------------------------------------------------------


class ScriptedSignalStrategy(Strategy):
    """Emits a scripted sequence of ``(action, strength)`` signals, one per bar."""

    def __init__(self, script: list[tuple[str, float]], symbols: list[str]):
        super().__init__(name="Scripted")
        self._script = list(script)
        self._symbols = list(symbols)
        self._index = 0

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._index >= len(self._script):
            return []
        action, strength = self._script[self._index]
        symbol = self._symbols[self._index % len(self._symbols)]
        self._index += 1
        price = float(data[symbol]["close"].iloc[-1])
        return [Signal(symbol=symbol, action=action, strength=strength, price=price)]


class SameBarSignalStrategy(Strategy):
    """Emits every scripted signal inside the first bar it is called for."""

    def __init__(self, script: list[tuple[str, float]], symbols: list[str]):
        super().__init__(name="SameBar")
        self._script = list(script)
        self._symbols = list(symbols)
        self._done = False

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._done:
            return []
        self._done = True
        signals = []
        for offset, (action, strength) in enumerate(self._script):
            symbol = self._symbols[offset % len(self._symbols)]
            price = float(data[symbol]["close"].iloc[-1])
            signals.append(Signal(symbol=symbol, action=action, strength=strength, price=price))
        return signals


def _price_frame(prices: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    """Build an OHLC frame with the given close prices."""
    index = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [price * 1.01 for price in prices],
            "low": [price * 0.99 for price in prices],
            "close": prices,
        },
        index=index,
    )


def _run_script(
    script: list[tuple[str, float]],
    data: dict[str, pd.DataFrame],
    config: Config | None = None,
    same_bar: bool = False,
    risk_manager: RiskManager | None = None,
) -> tuple[BacktestResult, BacktestEngine]:
    """Run a scripted backtest and return its result and the engine."""
    symbols = list(data.keys())
    provider = MockDataProvider(data)
    engine = BacktestEngine(
        config=config,
        data_manager=DataManager([provider]),
        risk_manager=risk_manager,
    )
    strategy = (
        SameBarSignalStrategy(script, symbols)
        if same_bar
        else ScriptedSignalStrategy(script, symbols)
    )
    engine.add_strategy(strategy)
    index = next(iter(data.values())).index
    result = engine.run(
        symbols,
        index[0].to_pydatetime(),
        index[-1].to_pydatetime(),
        "1d",
    )
    return result, engine


def _short_config(**risk: float) -> Config:
    """Build a config whose risk limits are given as keyword arguments."""
    return Config(
        backtest=BacktestConfig(initial_capital=100000.0),
        risk=RiskConfig(**risk),
    )


def test_short_signal_opens_a_short_sized_by_the_position_limit():
    """A short signal opens a short of the size the position limit allows."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _ = _run_script([("short", 1.0)], data, config)

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["action"] == "short"
    # 10% of 100000 at 50.00 a unit.
    assert trade["quantity"] == pytest.approx(200.0)
    assert trade["price"] == pytest.approx(50.0)
    # The position is short and the sale credited its proceeds to cash.
    assert result.positions["TEST"].quantity == pytest.approx(-200.0)
    assert result.positions["TEST"].avg_price == pytest.approx(50.0)


def test_short_entry_books_the_fee_it_pays():
    """The entry fee of a short is charged to cash and booked as realized PnL."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, engine = _run_script([("short", 1.0)], data, config)

    trade = result.trades.iloc[0]
    expected_fee = (
        trade["quantity"] * trade["price"] * (config.backtest.commission + config.backtest.slippage)
    )
    assert trade["fee"] == pytest.approx(expected_fee)
    # A short keeps the raw execution price as its basis, so the entry fee is
    # booked as realized PnL on the trade that paid it.
    assert trade["pnl"] == pytest.approx(-expected_fee)
    # The fee left the cash balance.
    assert engine.portfolio.cash == pytest.approx(
        result.initial_capital + trade["quantity"] * trade["price"] - expected_fee
    )


def test_short_round_trip_reconciles_cash_pnl_and_equity():
    """A short that is covered again books the PnL, the cash and the equity."""
    data = {"TEST": _price_frame([50.0, 50.0, 40.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, engine = _run_script([("short", 1.0), ("hold", 0.0), ("buy", 1.0)], data, config)

    assert len(result.trades) == 2
    short = result.trades.iloc[0]
    cover = result.trades.iloc[1]
    assert short["action"] == "short"
    assert cover["action"] == "cover"
    assert cover["price"] == pytest.approx(40.0)

    # The position is flat again.
    assert result.positions == {}

    # The round trip paid the price move minus the fee of both legs.
    fees = short["fee"] + cover["fee"]
    expected_pnl = short["quantity"] * (50.0 - 40.0) - fees
    assert result.trades["pnl"].sum() == pytest.approx(expected_pnl)

    # The cash moved by exactly the signed trade costs.
    signed_cost = short["cost"] - cover["cost"]
    assert engine.portfolio.cash - result.initial_capital == pytest.approx(signed_cost)
    assert result.final_value == pytest.approx(result.initial_capital + signed_cost)
    assert result.equity_curve.iloc[-1] == pytest.approx(result.final_value)


def test_buy_signal_covers_an_open_short():
    """A buy signal against an open short buys it back."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, engine = _run_script([("short", 1.0), ("hold", 0.0), ("buy", 1.0)], data, config)

    cover = result.trades.iloc[1]
    assert cover["action"] == "cover"
    # The whole short was covered, so the position is flat again.
    assert cover["quantity"] == pytest.approx(result.trades.iloc[0]["quantity"])
    assert result.positions == {}
    assert engine.portfolio.holdings == {}


def test_cover_can_be_smaller_than_the_open_short():
    """A cover with a strength below one closes only that part of the short."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _ = _run_script([("short", 1.0), ("hold", 0.0), ("buy", 0.5)], data, config)

    short = result.trades.iloc[0]
    cover = result.trades.iloc[1]
    assert cover["quantity"] == pytest.approx(short["quantity"] / 2)
    # The rest of the short is still open.
    assert result.positions["TEST"].quantity == pytest.approx(-short["quantity"] / 2)


def test_oversized_short_is_rejected_by_the_signal_gate():
    """A short that would breach the position limit is not traded."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, engine = _run_script([("short", 2.0)], data, config)

    assert result.trades.empty
    assert engine.portfolio.holdings == {}


def test_short_that_would_breach_the_leverage_limit_is_rejected():
    """A short is measured on gross exposure, so it cannot hide behind a long."""
    data = {
        "AAA": _price_frame([50.0, 50.0]),
        "BBB": _price_frame([50.0, 50.0]),
    }
    config = _short_config(max_position_size=0.5, max_leverage=0.75, max_portfolio_risk=1.0)

    result, _ = _run_script([("buy", 1.0), ("short", 1.0)], data, config, same_bar=True)

    # The long filled 0.5x of the portfolio; the short would add another
    # 0.5x of gross exposure, which is above the 0.75x limit.
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["action"] == "buy"
    assert result.positions["AAA"].quantity > 0
    assert "BBB" not in result.positions


def test_long_and_short_pair_is_measured_on_gross_exposure():
    """An equally sized long and short do not cancel each other out."""
    data = {
        "AAA": _price_frame([50.0, 50.0]),
        "BBB": _price_frame([50.0, 50.0]),
    }
    config = _short_config(max_position_size=0.5, max_leverage=0.75, max_portfolio_risk=1.0)

    result, _ = _run_script([("short", 1.0), ("buy", 1.0)], data, config, same_bar=True)

    # Net exposure would be zero, gross exposure is 1.0x, so the second
    # trade is rejected by the leverage limit.
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["action"] == "short"
    assert result.positions["AAA"].quantity < 0
    assert "BBB" not in result.positions


def test_second_short_in_the_same_bar_is_measured_against_the_first():
    """A second short in the same bar is measured against the exposure it adds."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.25, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _ = _run_script([("short", 1.0), ("short", 1.0)], data, config, same_bar=True)

    # The first short filled the position limit, so the second one has no
    # room left and is not traded.
    assert len(result.trades) == 1
    assert result.positions["TEST"].quantity == pytest.approx(-500.0)


def test_sell_signal_does_not_add_to_an_open_short():
    """A sell signal is not a way to short: an open short is left alone."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _ = _run_script([("short", 1.0), ("hold", 0.0), ("sell", 1.0)], data, config)

    assert len(result.trades) == 1
    assert result.positions["TEST"].quantity < 0


def test_short_signal_is_rejected_while_a_long_position_is_open():
    """A short signal does not flip an open long position."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _ = _run_script([("buy", 1.0), ("short", 1.0)], data, config, same_bar=True)

    assert len(result.trades) == 1
    assert result.trades.iloc[0]["action"] == "buy"
    assert result.positions["TEST"].quantity > 0


def test_engine_short_gets_mirrored_stop_loss_and_take_profit():
    """The risk manager's thresholds follow the direction of a short."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(
        max_position_size=0.1,
        max_leverage=1.0,
        max_portfolio_risk=1.0,
        stop_loss_pct=0.10,
        take_profit_pct=0.20,
    )

    result, engine = _run_script([("short", 1.0)], data, config)

    position = result.positions["TEST"]
    assert position.quantity < 0
    avg_price = position.avg_price
    rm = engine.risk_manager
    # The manager's own view of the position agrees with the result.
    assert rm.positions["TEST"].quantity < 0
    # A short's stop is above its entry price and its target below it.
    assert rm.get_position_stop_loss("TEST") == pytest.approx(avg_price * 1.10)
    assert rm.get_position_take_profit("TEST") == pytest.approx(avg_price * 0.80)
    assert rm.should_stop_loss("TEST", avg_price * 1.10) is True
    assert rm.should_take_profit("TEST", avg_price * 1.10) is False
    assert rm.should_take_profit("TEST", avg_price * 0.80) is True
    assert rm.should_stop_loss("TEST", avg_price * 0.80) is False


def test_trailing_stop_config_reaches_the_risk_manager():
    """The trailing stop settings of the risk config are forwarded to the manager."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(
        max_position_size=0.1,
        max_leverage=1.0,
        max_portfolio_risk=1.0,
        trailing_stop_pct=0.05,
        trailing_stop_activation_pct=0.02,
    )

    _, engine = _run_script([("buy", 1.0)], data, config)

    rm = engine.risk_manager
    assert rm.trailing_stop_pct == 0.05
    assert rm.trailing_stop_activation_pct == 0.02


def test_engine_tracks_a_trailing_stop_while_the_price_rises():
    """The trailing stop of a long follows the price the engine observes."""
    data = {"TEST": _price_frame([50.0, 60.0, 70.0])}
    config = _short_config(
        max_position_size=0.1,
        max_leverage=1.0,
        max_portfolio_risk=1.0,
        stop_loss_pct=0.20,
        trailing_stop_pct=0.10,
    )

    result, engine = _run_script([("buy", 1.0)], data, config)

    rm = engine.risk_manager
    position = result.positions["TEST"]
    assert position.quantity > 0
    # The stop follows the highest price the position reached (70.0).
    assert rm.get_trailing_stop("TEST") == pytest.approx(63.0)
    assert rm.get_position_stop_loss("TEST") == pytest.approx(63.0)
    assert rm.should_stop_loss("TEST", 63.0) is True
    assert rm.should_stop_loss("TEST", 64.0) is False


def test_short_and_cover_in_the_same_bar_end_flat():
    """A short that is covered inside the same bar leaves no position behind."""
    data = {"TEST": _price_frame([50.0, 50.0])}
    config = _short_config(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0)

    result, _engine = _run_script([("short", 1.0), ("buy", 1.0)], data, config, same_bar=True)

    assert len(result.trades) == 2
    assert result.trades.iloc[0]["action"] == "short"
    assert result.trades.iloc[1]["action"] == "cover"
    assert result.positions == {}
    # Only the fees were paid, the price did not move.
    assert result.final_value == pytest.approx(result.initial_capital - result.total_costs)


def test_process_signal_short_executes_a_trade():
    """A short signal is executed directly against the engine."""
    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    short = Signal(symbol="AAPL", action="short", strength=1.0, price=150.0)
    trades: list[Trade] = []

    engine._process_signal(short, trades, datetime.now())

    assert len(trades) == 1
    assert trades[0].action == "short"
    assert trades[0].quantity > 0
    assert engine.portfolio.get_position("AAPL").quantity == pytest.approx(-trades[0].quantity)


def test_process_signal_short_without_price_is_skipped():
    """A short signal without a usable price is skipped."""
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    short = Signal(symbol="AAPL", action="short", strength=1.0, price=0.0)
    trades: list[Trade] = []

    engine._process_signal(short, trades, datetime.now())

    assert trades == []


def test_process_signal_buy_covers_an_open_short():
    """A buy signal against an open short covers it instead of flipping it."""
    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)
    engine.risk_manager.disable()
    engine.portfolio.add_holding("AAPL", -100.0, 150.0)
    buy = Signal(symbol="AAPL", action="buy", strength=1.0, price=140.0)
    trades: list[Trade] = []

    engine._process_signal(buy, trades, datetime.now())

    assert len(trades) == 1
    assert trades[0].action == "cover"
    # The short was covered, not flipped into a long.
    assert trades[0].quantity == pytest.approx(100.0)
    assert engine.portfolio.get_position("AAPL") is None


def _top_up_config() -> Config:
    """Build a config with fee-free fills and a 10% position limit."""
    return Config(
        backtest=BacktestConfig(initial_capital=100000.0, commission=0.0, slippage=0.0),
        risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
    )


def test_buy_signal_tops_up_a_position_below_its_target():
    """A position that is part of the way to its target is topped up.

    The signal gate measures the exposure the position carries after the
    trade, so a position that is below its target does not block the signal
    that would bring it up to the target.
    """
    data = {"TEST": _price_frame([50.0, 50.0, 50.0])}

    result, _engine = _run_script([("buy", 0.5), ("buy", 1.0)], data, _top_up_config())

    # The first buy fills half of the position limit, the second tops the
    # position up to the full limit.
    assert len(result.trades) == 2
    assert result.trades.iloc[1]["quantity"] == pytest.approx(100.0)
    assert result.positions["TEST"].quantity == pytest.approx(200.0)


def test_short_signal_tops_up_a_short_below_its_target():
    """A short that is part of the way to its target is topped up."""
    data = {"TEST": _price_frame([50.0, 50.0, 50.0])}

    result, _engine = _run_script([("short", 0.5), ("short", 1.0)], data, _top_up_config())

    assert len(result.trades) == 2
    assert result.trades.iloc[1]["quantity"] == pytest.approx(100.0)
    assert result.positions["TEST"].quantity == pytest.approx(-200.0)


# ---------------------------------------------------------------------------
# Stop exits
# ---------------------------------------------------------------------------


def _stop_exit_config(
    commission: float = 0.0,
    slippage: float = 0.0,
    **risk: float,
) -> Config:
    """Build a config whose stop exits are enabled."""
    limits: dict[str, float] = {
        "max_position_size": 0.1,
        "max_leverage": 1.0,
        "max_portfolio_risk": 1.0,
    }
    limits.update(risk)
    return Config(
        backtest=BacktestConfig(
            initial_capital=100000.0,
            commission=commission,
            slippage=slippage,
            enable_stop_exits=True,
        ),
        risk=RiskConfig(**limits),
    )


def test_stop_loss_closes_a_long_at_the_bar_close():
    """A long whose close falls to its stop loss is closed at that close."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = _stop_exit_config(stop_loss_pct=0.05, take_profit_pct=0.15)

    result, _engine = _run_script([("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    entry = result.trades.iloc[0]
    exit_trade = result.trades.iloc[1]
    assert entry["action"] == "buy"
    assert exit_trade["action"] == "sell"
    # The stop is 5% below the entry price of 50.00, so the close of 45.00
    # is below it and the position is closed there.
    assert exit_trade["price"] == pytest.approx(45.0)
    assert exit_trade["quantity"] == pytest.approx(entry["quantity"])
    # The position is flat afterwards.
    assert result.positions == {}


def test_take_profit_closes_a_long_at_the_bar_close():
    """A long whose close rises to its take profit is closed at that close."""
    data = {"TEST": _price_frame([50.0, 50.0, 60.0])}
    config = _stop_exit_config(stop_loss_pct=0.05, take_profit_pct=0.15)

    result, _engine = _run_script([("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    exit_trade = result.trades.iloc[1]
    assert exit_trade["action"] == "sell"
    # The target is 15% above the entry price of 50.00.
    assert exit_trade["price"] == pytest.approx(60.0)
    assert result.positions == {}


def test_stop_loss_covers_a_short_at_the_bar_close():
    """A short whose close rises to its stop loss is covered at that close."""
    data = {"TEST": _price_frame([50.0, 50.0, 55.0])}
    config = _stop_exit_config(stop_loss_pct=0.05, take_profit_pct=0.15)

    result, _engine = _run_script([("short", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    entry = result.trades.iloc[0]
    exit_trade = result.trades.iloc[1]
    assert entry["action"] == "short"
    assert exit_trade["action"] == "cover"
    # The stop of a short is 5% above its entry price of 50.00.
    assert exit_trade["price"] == pytest.approx(55.0)
    assert exit_trade["quantity"] == pytest.approx(entry["quantity"])
    assert result.positions == {}


def test_take_profit_covers_a_short_at_the_bar_close():
    """A short whose close falls to its take profit is covered at that close."""
    data = {"TEST": _price_frame([50.0, 50.0, 40.0])}
    config = _stop_exit_config(stop_loss_pct=0.05, take_profit_pct=0.15)

    result, _engine = _run_script([("short", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    exit_trade = result.trades.iloc[1]
    assert exit_trade["action"] == "cover"
    # The target of a short is 15% below its entry price of 50.00.
    assert exit_trade["price"] == pytest.approx(40.0)
    assert result.positions == {}


def test_trailing_stop_closes_a_long_on_a_later_bar():
    """A trailing stop closes a long on a bar after the one that ratcheted it."""
    data = {"TEST": _price_frame([50.0, 60.0, 55.0])}
    config = _stop_exit_config(
        stop_loss_pct=0.5,
        take_profit_pct=1.0,
        trailing_stop_pct=0.05,
    )

    result, _engine = _run_script([("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    exit_trade = result.trades.iloc[1]
    assert exit_trade["action"] == "sell"
    # The stop trailed the high of 60.00 down to 57.00, so the close of
    # 55.00 on the next bar is below it.
    assert exit_trade["price"] == pytest.approx(55.0)
    assert exit_trade["timestamp"] == data["TEST"].index[2].to_pydatetime()
    assert result.positions == {}


def test_stop_exit_keeps_the_accounting_invariant():
    """A run that is closed by a stop still reconciles cash, PnL and equity."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = _stop_exit_config(commission=0.001, slippage=0.0005)

    result, engine = _run_script([("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    assert len(result.trades) == 2
    assert result.positions == {}
    assert result.final_value - result.initial_capital == pytest.approx(result.trades["pnl"].sum())
    assert engine.portfolio.cash - result.initial_capital == pytest.approx(
        result.trades["cost"].iloc[1] - result.trades["cost"].iloc[0]
    )
    assert result.equity_curve.iloc[-1] == pytest.approx(result.final_value)


def test_stop_exits_are_off_by_default():
    """Without the flag the stop levels stay advisory and the position stays open."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    config = Config(
        backtest=BacktestConfig(initial_capital=100000.0),
        risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
    )

    result, _engine = _run_script([("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data, config)

    # Only the entry was traded, the position was not stopped out.
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["action"] == "buy"
    assert result.positions["TEST"].quantity == pytest.approx(200.0)


def test_a_bar_that_hits_both_levels_closes_the_position_once():
    """A close that hits the stop and the target closes the position once."""
    data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
    # The target is placed below the entry price, so the close of 45.00 hits
    # both the stop at 47.50 and the target at 42.50.
    risk_manager = RiskManager(
        initial_capital=100000.0,
        max_position_size=0.1,
        max_leverage=1.0,
        max_portfolio_risk=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=-0.15,
    )

    result, _engine = _run_script(
        [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)],
        data,
        _stop_exit_config(),
        risk_manager=risk_manager,
    )

    assert len(result.trades) == 2
    assert result.trades.iloc[1]["action"] == "sell"
    assert result.positions == {}


class TestRunBacktestAppliesConfig:
    """``run_backtest()`` applies the sections of the configuration it is given.

    A full ``Config`` carries the backtest settings, the risk limits and the
    position limit of a run. ``run_backtest()`` used to read the data section
    of it only, so the ``risk`` and the ``portfolio`` sections were silently
    dropped: a configuration that allowed a single position was ignored and
    the run opened as many positions as it could.

    The precedence is the same everywhere: a value that is passed explicitly
    wins over the configured one, and the configured one wins over the
    built-in default.
    """

    @staticmethod
    def _run(
        config,
        script: list[tuple[str, float]],
        data: dict[str, pd.DataFrame],
        same_bar: bool = False,
        **kwargs,
    ) -> BacktestResult:
        """Run a scripted backtest through ``run_backtest()``."""
        symbols = list(data.keys())
        index = next(iter(data.values())).index
        strategy = (
            SameBarSignalStrategy(script, symbols)
            if same_bar
            else ScriptedSignalStrategy(script, symbols)
        )
        return run_backtest(
            strategy=strategy,
            symbols=symbols,
            start=index[0].to_pydatetime(),
            end=index[-1].to_pydatetime(),
            config=config,
            data_manager=DataManager([MockDataProvider(data)]),
            **kwargs,
        )

    def test_the_risk_section_of_the_config_sizes_the_positions(self):
        """The configured position limit sizes the positions of the run."""
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0),
            risk=RiskConfig(max_position_size=0.01, max_leverage=1.0, max_portfolio_risk=1.0),
        )

        result = self._run(config, [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data)

        assert len(result.trades) == 1
        trade = result.trades.iloc[0]
        # 1% of a portfolio of 100000.00, at a price of 50.00 a unit.
        assert trade["quantity"] * trade["price"] == pytest.approx(1000.0)

    def test_the_portfolio_section_of_the_config_limits_the_number_of_positions(self):
        """The configured position limit caps the number of open positions."""
        data = {
            "A": _price_frame([50.0, 50.0, 50.0]),
            "B": _price_frame([50.0, 50.0, 50.0]),
        }
        script = [("buy", 1.0), ("buy", 1.0)]
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
            portfolio=PortfolioConfig(max_positions=1),
        )

        result = self._run(config, script, data, same_bar=True)

        # The second buy is rejected by the signal gate, so only the first
        # symbol is held.
        assert len(result.trades) == 1
        assert set(result.positions) == {"A"}

    def test_the_portfolio_section_allows_the_positions_it_permits(self):
        """The same run opens both positions when the limit allows them."""
        data = {
            "A": _price_frame([50.0, 50.0, 50.0]),
            "B": _price_frame([50.0, 50.0, 50.0]),
        }
        script = [("buy", 1.0), ("buy", 1.0)]
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
            portfolio=PortfolioConfig(max_positions=2),
        )

        result = self._run(config, script, data, same_bar=True)

        assert len(result.trades) == 2
        assert set(result.positions) == {"A", "B"}

    def test_the_backtest_section_of_the_config_switches_the_stop_exits_on(self):
        """The configured switch closes the position whose stop was hit."""
        data = {"TEST": _price_frame([50.0, 50.0, 45.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0, enable_stop_exits=True),
            risk=RiskConfig(
                max_position_size=0.1,
                max_leverage=1.0,
                max_portfolio_risk=1.0,
                stop_loss_pct=0.05,
                take_profit_pct=0.15,
            ),
        )

        result = self._run(config, [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data)

        assert len(result.trades) == 2
        exit_trade = result.trades.iloc[1]
        assert exit_trade["action"] == "sell"
        assert exit_trade["price"] == pytest.approx(45.0)
        assert result.positions == {}

    def test_the_configured_initial_capital_is_used(self):
        """The configured starting capital is the one the run is driven by."""
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=50000.0),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
        )

        result = self._run(config, [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data)

        assert result.initial_capital == 50000.0
        trade = result.trades.iloc[0]
        # 10% of a portfolio of 50000.00, at a price of 50.00 a unit.
        assert trade["quantity"] * trade["price"] == pytest.approx(5000.0)

    def test_an_explicit_value_wins_over_the_configured_one(self):
        """A value that is passed explicitly wins over the configured one."""
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=50000.0, commission=0.01, slippage=0.01),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
        )

        result = self._run(
            config,
            [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)],
            data,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
        )

        assert result.initial_capital == 100000.0
        trade = result.trades.iloc[0]
        # 10% of a portfolio of 100000.00, at a price of 50.00 a unit.
        assert trade["quantity"] * trade["price"] == pytest.approx(10000.0)
        assert trade["fee"] == pytest.approx(200.0 * 50.0 * 0.0015)

    def test_the_configured_periods_per_year_is_used(self):
        """The configured annualization period reaches the metrics."""
        data = {"TEST": _price_frame([50.0, 51.0, 52.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0, periods_per_year=12),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
        )

        result = self._run(config, [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)], data)

        returns = result.equity_curve.pct_change().dropna()
        assert result.metrics.annual_return == pytest.approx(returns.mean() * 12)
        assert result.metrics.volatility == pytest.approx(returns.std() * (12**0.5))

    def test_the_config_is_not_modified_by_the_run(self):
        """The configuration of the caller is left untouched by the run."""
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        config = Config(
            backtest=BacktestConfig(initial_capital=100000.0, periods_per_year=252),
            risk=RiskConfig(max_position_size=0.1, max_leverage=1.0, max_portfolio_risk=1.0),
        )

        self._run(
            config,
            [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)],
            data,
            initial_capital=250000.0,
            periods_per_year=12,
        )

        assert config.backtest.initial_capital == 100000.0
        assert config.backtest.periods_per_year == 252

    def test_a_data_config_leaves_the_backtest_settings_at_their_defaults(self):
        """A data configuration does not change the backtest settings."""
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        data_config = DataConfig(provider="synthetic", offline=True)

        result = self._run(
            data_config,
            [("buy", 1.0), ("hold", 0.0), ("hold", 0.0)],
            data,
        )

        assert result.initial_capital == 100000.0
        trade = result.trades.iloc[0]
        # 10% of the default portfolio of 100000.00.
        assert trade["quantity"] * trade["price"] == pytest.approx(10000.0)


class TestDrawdownGateEndToEnd:
    """A backtest in a drawdown breach stops opening new positions.

    The signal gate refuses a signal that adds exposure while the portfolio is
    in a breach of its drawdown limit. A run that falls into such a breach
    therefore keeps the positions it already holds and opens no new one, while
    the positions that are already open are still closed by their own exit
    signals.

    The run below buys ``A`` on the first bar and ``B`` on the second one.
    ``A`` then loses 60% of its value, which puts the portfolio 24% below its
    peak, so the third bar is not allowed to open ``C``. The fourth bar sells
    ``A``, which reduces the exposure and is therefore still allowed.
    """

    def _data(self) -> dict[str, pd.DataFrame]:
        return {
            "A": _price_frame([50.0, 20.0, 20.0, 20.0, 20.0]),
            "B": _price_frame([50.0, 50.0, 50.0, 50.0, 50.0]),
            "C": _price_frame([50.0, 50.0, 50.0, 50.0, 50.0]),
        }

    def _config(self, max_drawdown: float) -> Config:
        return Config(
            backtest=BacktestConfig(initial_capital=100000.0, commission=0.0, slippage=0.0),
            risk=RiskConfig(
                max_position_size=0.4,
                max_portfolio_risk=0.5,
                max_leverage=5.0,
                max_drawdown=max_drawdown,
            ),
        )

    def test_a_run_in_a_drawdown_breach_opens_no_new_position(self):
        script = [("buy", 1.0), ("buy", 1.0), ("buy", 1.0), ("sell", 1.0)]

        result, _ = _run_script(script, self._data(), self._config(0.20))

        # The third bar would have bought "C", but the portfolio is 24% below
        # its peak, so the gate rejected that signal.
        assert list(result.trades["symbol"]) == ["A", "B", "A"]
        assert list(result.trades["action"]) == ["buy", "buy", "sell"]
        assert "C" not in set(result.trades["symbol"])
        # The position that was open is still closed by its own exit signal.
        assert "A" not in result.positions
        assert result.positions["B"].quantity > 0

    def test_the_drawdown_breach_is_reported_by_the_portfolio_check(self):
        script = [("buy", 1.0), ("buy", 1.0), ("buy", 1.0), ("sell", 1.0)]

        result, _ = _run_script(script, self._data(), self._config(0.20))

        assert any("Drawdown" in violation for violation in result.portfolio_violations)

    def test_a_run_without_a_drawdown_limit_opens_the_position(self):
        """The control: the same run opens "C" when the limit is disabled."""
        script = [("buy", 1.0), ("buy", 1.0), ("buy", 1.0), ("sell", 1.0)]

        result, _ = _run_script(script, self._data(), self._config(0.0))

        assert list(result.trades["symbol"]) == ["A", "B", "C", "A"]
        assert list(result.trades["action"]) == ["buy", "buy", "buy", "sell"]


class RecordingMockDataProvider(DataProvider):
    """Mock data provider that records the intervals it was fetched with."""

    def __init__(self, data: dict):
        self._data = data
        self._name = "mock"
        self.fetched_intervals: list[str] = []

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
        self.fetched_intervals.append(interval)
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


class TestDataIntervalConfig:
    """``run_backtest()`` fetches with the interval the configuration carries.

    ``default_interval`` of the data section was defined, documented and
    exported, but nothing read it: the interval a run actually used came from
    a hard-coded default, so a configuration that asked for weekly bars was
    silently ignored. The precedence is the same everywhere: a value that is
    passed explicitly wins over the configured one, and the configured one
    wins over the built-in default.
    """

    @staticmethod
    def _run(config, interval=None) -> list[str]:
        data = {"TEST": _price_frame([50.0, 50.0, 50.0])}
        provider = RecordingMockDataProvider(data)
        manager = DataManager([provider])
        strategy = FirstDayBuyStrategy()
        index = next(iter(data.values())).index
        run_backtest(
            strategy=strategy,
            symbols=["TEST"],
            start=index[0].to_pydatetime(),
            end=index[-1].to_pydatetime(),
            config=config,
            data_manager=manager,
            interval=interval,
        )
        return provider.fetched_intervals

    def test_the_configured_default_interval_is_used(self):
        """The configured interval is the one the run fetches with."""
        config = Config(data=DataConfig(default_interval="1wk"))
        assert self._run(config) == ["1wk"]

    def test_an_explicit_interval_wins_over_the_configured_one(self):
        """An explicit interval overrides the configured one."""
        config = Config(data=DataConfig(default_interval="1wk"))
        assert self._run(config, interval="1d") == ["1d"]

    def test_a_data_config_configures_the_interval(self):
        """A DataConfig alone carries the interval for the run."""
        config = DataConfig(default_interval="1h")
        assert self._run(config) == ["1h"]

    def test_the_built_in_default_is_used_when_nothing_is_configured(self):
        """No configuration falls back to the built-in default of "1d"."""
        assert self._run(None) == ["1d"]

    def test_the_configuration_of_the_caller_is_not_modified(self):
        """The resolved interval does not touch the caller's configuration."""
        config = Config(data=DataConfig(default_interval="1wk"))
        self._run(config, interval="1d")
        assert config.data.default_interval == "1wk"


class TestStopExitAndShortCoveringEdges:
    """Tests for the defensive branches of the engine's exit and sizing logic.

    These branches are guards that only trigger in unusual states (a held
    symbol with no price on the bar, a zero-quantity holding, a short sized
    against an exhausted budget, a cover with zero size, or a cover trimmed to
    zero by an empty cash balance). They are exercised by driving the engine's
    private methods directly with a hand-built portfolio so no network or
    full backtest run is required.
    """

    def _engine(self) -> BacktestEngine:
        return BacktestEngine(config=BacktestConfig(initial_capital=100_000.0))

    def _timestamp(self) -> datetime:
        return datetime(2024, 1, 1)

    def test_process_stop_exits_skips_symbol_without_price(self):
        """A held symbol missing from the bar's prices is skipped (line 647)."""
        engine = self._engine()
        engine.portfolio.holdings["AAPL"] = Holding(
            symbol="AAPL", quantity=100, avg_cost=100.0, current_price=100.0
        )
        trades: list[Trade] = []
        engine._process_stop_exits(
            prices={"MSFT": 100.0}, trades_list=trades, timestamp=self._timestamp()
        )
        assert trades == []
        assert "AAPL" in engine.portfolio.holdings

    def test_process_stop_exits_skips_zero_quantity_holding(self):
        """A holding with zero quantity is skipped (line 651)."""
        engine = self._engine()
        engine.portfolio.holdings["AAPL"] = Holding(
            symbol="AAPL", quantity=0, avg_cost=100.0, current_price=100.0
        )
        trades: list[Trade] = []
        engine._process_stop_exits(
            prices={"AAPL": 100.0}, trades_list=trades, timestamp=self._timestamp()
        )
        assert trades == []
        assert engine.portfolio.holdings["AAPL"].quantity == 0

    def test_open_short_returns_when_no_available_value(self):
        """A short with no available position value is not opened (line 845)."""
        engine = self._engine()
        signal = Signal(symbol="AAPL", action="sell", strength=0.0, price=100.0)
        trades: list[Trade] = []
        engine._open_short(
            symbol="AAPL",
            signal=signal,
            trades_list=trades,
            timestamp=self._timestamp(),
            price=100.0,
        )
        assert trades == []
        assert "AAPL" not in engine.portfolio.holdings

    def test_cover_short_returns_when_zero_quantity(self):
        """A cover signal with zero strength covers nothing (line 906)."""
        engine = self._engine()
        engine.portfolio.holdings["AAPL"] = Holding(
            symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=100.0
        )
        holding = engine.portfolio.holdings["AAPL"]
        signal = Signal(symbol="AAPL", action="buy", strength=0.0, price=100.0)
        trades: list[Trade] = []
        engine._cover_short(
            symbol="AAPL",
            signal=signal,
            trades_list=trades,
            timestamp=self._timestamp(),
            price=100.0,
            holding=holding,
        )
        assert trades == []
        assert engine.portfolio.holdings["AAPL"].quantity == -100

    def test_cover_short_returns_when_cash_constrained_to_zero(self):
        """A cover trimmed to zero cash is not executed (lines 910-914)."""
        engine = self._engine()
        engine.portfolio.cash = 0.0
        engine.portfolio.holdings["AAPL"] = Holding(
            symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=100.0
        )
        holding = engine.portfolio.holdings["AAPL"]
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        trades: list[Trade] = []
        engine._cover_short(
            symbol="AAPL",
            signal=signal,
            trades_list=trades,
            timestamp=self._timestamp(),
            price=100.0,
            holding=holding,
        )
        assert trades == []
        assert engine.portfolio.holdings["AAPL"].quantity == -100

    def test_cover_short_trims_to_affordable_positive_quantity(self):
        """A cover trimmed by cash still executes when the trimmed size is positive (line 915 not taken)."""
        engine = self._engine()
        engine.portfolio.cash = 50.0
        engine.portfolio.holdings["AAPL"] = Holding(
            symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=100.0
        )
        holding = engine.portfolio.holdings["AAPL"]
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        trades: list[Trade] = []
        engine._cover_short(
            symbol="AAPL",
            signal=signal,
            trades_list=trades,
            timestamp=self._timestamp(),
            price=100.0,
            holding=holding,
        )
        assert len(trades) == 1
        assert trades[0].action == "cover"
        assert 0 < trades[0].quantity < 100
        assert engine.portfolio.holdings["AAPL"].quantity == -100 + trades[0].quantity
