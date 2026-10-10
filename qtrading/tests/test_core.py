from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from qtrading.backtest import BacktestEngine, BacktestResult, Portfolio
from qtrading.config import (
    BacktestConfig,
    DataConfig,
    ExecutionConfig,
    MonitoringConfig,
    RiskConfig,
    Settings,
    TradingConfig,
)
from qtrading.data import OHLCV, Exchange, OrderBook, Ticker, Timeframe
from qtrading.execution import (
    ExecutionReport,
    OrderRouter,
    PortfolioManager,
    SimulationEngine,
)
from qtrading.risk import RiskManager
from qtrading.strategy import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SignalType,
    StrategyContext,
    StrategyParams,
    StrategyRegistry,
)
from qtrading.strategy.builtin import MeanReversionStrategy, RSIStrategy, SMACrossoverStrategy


class TestDataModels:
    def test_ohlcv_creation(self):
        ohlcv = OHLCV(
            timestamp=datetime.now(UTC),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            exchange=Exchange.BINANCE,
        )
        assert ohlcv.symbol == "BTC/USDT"
        assert ohlcv.close == Decimal("50500")

    def test_ticker_creation(self):
        ticker = Ticker(
            symbol="BTC/USDT",
            bid=Decimal("50000"),
            ask=Decimal("50001"),
            last=Decimal("50000.5"),
            volume=Decimal("1000"),
            timestamp=datetime.now(UTC),
            exchange=Exchange.BINANCE,
        )
        assert ticker.spread == Decimal("1")
        assert ticker.mid == Decimal("50000.5")

    def test_orderbook_creation(self):
        ob = OrderBook(
            symbol="BTC/USDT",
            bids=[(Decimal("50000"), Decimal("1")), (Decimal("49999"), Decimal("2"))],
            asks=[(Decimal("50001"), Decimal("1")), (Decimal("50002"), Decimal("2"))],
            timestamp=datetime.now(UTC),
            exchange=Exchange.BINANCE,
        )
        assert ob.best_bid == Decimal("50000")
        assert ob.best_ask == Decimal("50001")
        assert ob.spread == Decimal("1")


class TestStrategyFramework:
    def test_strategy_params(self):
        params = StrategyParams(
            name="test_strategy",
            symbols=["BTC/USDT"],
            timeframes=["1h"],
            parameters={"fast_period": 10, "slow_period": 30},
        )
        assert params.name == "test_strategy"
        assert params.parameters["fast_period"] == 10

    def test_signal_creation(self):
        signal = Signal(
            symbol="BTC/USDT",
            signal_type=SignalType.BUY,
            strength=1.0,
            timestamp=datetime.now(UTC),
            price=Decimal("50000"),
            metadata={"test": True},
        )
        assert signal.signal_type == SignalType.BUY
        assert signal.strength == 1.0

    def test_order_creation(self):
        order = Order(
            id="test_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.PENDING

    def test_position_creation(self):
        position = Position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("51000"),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("0"),
            side="long",
            timestamp=datetime.now(UTC),
        )
        assert position.quantity == Decimal("0.1")
        assert position.unrealized_pnl == Decimal("100")

    def test_strategy_registry(self):
        strategies = StrategyRegistry.list_strategies()
        assert "sma_crossover" in strategies
        assert "mean_reversion" in strategies
        assert "rsi_strategy" in strategies

        strategy = StrategyRegistry.create("sma_crossover", StrategyParams(
            name="test",
            symbols=["BTC/USDT"],
            parameters={"fast_period": 10, "slow_period": 30},
        ))
        assert isinstance(strategy, SMACrossoverStrategy)


class TestBuiltinStrategies:
    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2024-01-01", periods=100, freq="1h")
        np.random.seed(42)
        close = 50000 + np.cumsum(np.random.randn(100) * 100)
        df = pd.DataFrame({
            "open": close + np.random.randn(100) * 10,
            "high": close + np.abs(np.random.randn(100) * 50),
            "low": close - np.abs(np.random.randn(100) * 50),
            "close": close,
            "volume": np.random.rand(100) * 100,
        }, index=dates)
        return {"BTC/USDT": df}

    @pytest.fixture
    def context(self, sample_data):
        return StrategyContext(
            current_time=datetime(2024, 1, 5, tzinfo=UTC),
            portfolio_value=Decimal("100000"),
            positions={},
            available_capital=Decimal("100000"),
            market_data=sample_data,
        )

    @pytest.mark.asyncio
    async def test_sma_crossover(self, context):
        strategy = SMACrossoverStrategy(StrategyParams(
            name="sma_test",
            symbols=["BTC/USDT"],
            parameters={"fast_period": 5, "slow_period": 20, "position_size": 0.1},
        ))
        signals = await strategy.run(context)
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_mean_reversion(self, context):
        strategy = MeanReversionStrategy(StrategyParams(
            name="mr_test",
            symbols=["BTC/USDT"],
            parameters={"lookback": 20, "entry_zscore": 2.0, "exit_zscore": 0.5, "position_size": 0.1},
        ))
        signals = await strategy.run(context)
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_rsi_strategy(self, context):
        strategy = RSIStrategy(StrategyParams(
            name="rsi_test",
            symbols=["BTC/USDT"],
            parameters={"period": 14, "overbought": 70, "oversold": 30, "position_size": 0.1},
        ))
        signals = await strategy.run(context)
        assert isinstance(signals, list)


class TestBacktestEngine:
    @pytest.fixture
    def sample_market_data(self):
        dates = pd.date_range("2024-01-01", periods=200, freq="1h")
        np.random.seed(42)
        trend = np.linspace(0, 5000, 200)
        noise = np.cumsum(np.random.randn(200) * 100)
        close = 50000 + trend + noise
        df = pd.DataFrame({
            "open": close + np.random.randn(200) * 10,
            "high": close + np.abs(np.random.randn(200) * 50),
            "low": close - np.abs(np.random.randn(200) * 50),
            "close": close,
            "volume": np.random.rand(200) * 100,
        }, index=dates)
        return {"BTC/USDT": df}

    def test_backtest_engine_initialization(self):
        engine = BacktestEngine(
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0005"),
        )
        assert engine.initial_capital == Decimal("100000")

    def test_backtest_run(self, sample_market_data):
        engine = BacktestEngine(initial_capital=Decimal("100000"))
        strategy = SMACrossoverStrategy(StrategyParams(
            name="sma_test",
            symbols=["BTC/USDT"],
            parameters={"fast_period": 10, "slow_period": 30, "position_size": 0.1},
        ))
        result = engine.run(strategy, sample_market_data)

        assert isinstance(result, BacktestResult)
        assert result.initial_capital == Decimal("100000")
        assert result.final_capital > Decimal("0")
        assert result.total_trades >= 0


class TestPortfolio:
    def test_portfolio_creation(self):
        portfolio = Portfolio(
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0005"),
        )
        assert portfolio.cash == Decimal("100000")
        assert portfolio.initial_capital == Decimal("100000")

    def test_portfolio_value_calculation(self):
        portfolio = Portfolio(
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0005"),
        )
        prices = {"BTC/USDT": Decimal("50000")}
        value = portfolio.get_portfolio_value(prices)
        assert value == Decimal("100000")


class TestRiskManager:
    def test_risk_manager_initialization(self):
        risk = RiskManager()
        assert risk.limits.max_drawdown == Decimal("0.15")
        assert risk.limits.max_position_size == Decimal("0.1")

    def test_position_size_check(self):
        risk = RiskManager()
        ok, err = risk.check_position_size(
            "BTC/USDT",
            Decimal("10"),
            Decimal("50000"),
            Decimal("100000"),
        )
        assert not ok
        assert "exceeds max" in err

        ok, err = risk.check_position_size(
            "BTC/USDT",
            Decimal("0.1"),
            Decimal("50000"),
            Decimal("100000"),
        )
        assert ok

    def test_drawdown_check(self):
        risk = RiskManager()
        risk.peak_value = Decimal("100000")

        ok, err = risk.check_drawdown(Decimal("90000"))
        assert ok

        ok, err = risk.check_drawdown(Decimal("80000"))
        assert not ok

    def test_daily_loss_check(self):
        risk = RiskManager()
        risk.daily_start_value = Decimal("100000")
        risk.daily_start_date = datetime.now()

        ok, err = risk.check_daily_loss(Decimal("96000"))
        assert ok

        ok, err = risk.check_daily_loss(Decimal("94000"))
        assert not ok


class TestExecution:
    @pytest.mark.asyncio
    async def test_simulation_engine_market_order(self):
        engine = SimulationEngine()
        engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="test_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        report = await engine.submit_order(order)
        assert report.status == OrderStatus.FILLED
        assert report.filled_quantity == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_simulation_engine_limit_order(self):
        engine = SimulationEngine()
        engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="test_2",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("49000"),
        )

        report = await engine.submit_order(order)
        assert report.status == OrderStatus.OPEN

        engine.update_price("BTC/USDT", Decimal("48000"))
        report = await engine.submit_order(order)
        assert report.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_order_router(self):
        router = OrderRouter()
        router.engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="test_3",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        report = await router.submit_order(order)
        assert report.status == OrderStatus.FILLED

    def test_portfolio_manager(self):
        pm = PortfolioManager(Decimal("100000"))

        report = ExecutionReport(
            order_id="test_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.1"),
            average_price=Decimal("50000"),
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
            commission=Decimal("5"),
            slippage=Decimal("2.5"),
        )

        pm.update_from_fill(report)
        assert pm.cash < Decimal("100000")
        assert pm.positions["BTC/USDT"] == Decimal("0.1")


class TestConfig:
    def test_settings_loading(self):
        settings = Settings(
            trading=TradingConfig(symbols=["BTC/USDT"], timeframes=["1h"], exchanges=["binance"]),
            data=DataConfig(),
            backtest=BacktestConfig(),
            risk=RiskConfig(),
            execution=ExecutionConfig(),
            monitoring=MonitoringConfig(),
        )
        assert settings.trading.symbols == ["BTC/USDT"]
        assert settings.backtest.initial_capital == 100000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
