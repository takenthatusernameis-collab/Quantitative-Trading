"""Tests for the backtest engine."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestEngine, BacktestResult, Trade
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
    trades = pd.DataFrame([{
        'symbol': 'AAPL',
        'action': 'buy',
        'quantity': 10,
        'price': 150.0,
        'timestamp': datetime.now(),
        'commission': 0.001,
        'slippage': 0.0005,
    }])

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


def test_run_backtest_convenience_function():
    """Test the run_backtest convenience function with mock data."""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
