from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from qtrading.backtest import BacktestEngine, BacktestResult, Portfolio, WalkForwardAnalyzer
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
    AlgorithmFactory,
    AlgorithmType,
    ExecutionAlgorithmConfig,
    ExecutionReport,
    ImplementationShortfallAlgorithm,
    OMSOrderState,
    OrderManager,
    OrderRouter,
    PaperTradingConfig,
    PaperTradingEngine,
    PortfolioManager,
    POVAlgorithm,
    RoutingStrategy,
    SimulationEngine,
    SmartOrderRouter,
    SmartOrderRouterConfig,
    TWAPAlgorithm,
    VenueConfig,
    VenueType,
    VWAPAlgorithm,
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

        strategy = StrategyRegistry.create(
            "sma_crossover",
            StrategyParams(
                name="test",
                symbols=["BTC/USDT"],
                parameters={"fast_period": 10, "slow_period": 30},
            ),
        )
        assert isinstance(strategy, SMACrossoverStrategy)


class TestBuiltinStrategies:
    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2024-01-01", periods=100, freq="1h")
        np.random.seed(42)
        close = 50000 + np.cumsum(np.random.randn(100) * 100)
        df = pd.DataFrame(
            {
                "open": close + np.random.randn(100) * 10,
                "high": close + np.abs(np.random.randn(100) * 50),
                "low": close - np.abs(np.random.randn(100) * 50),
                "close": close,
                "volume": np.random.rand(100) * 100,
            },
            index=dates,
        )
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
        strategy = SMACrossoverStrategy(
            StrategyParams(
                name="sma_test",
                symbols=["BTC/USDT"],
                parameters={"fast_period": 5, "slow_period": 20, "position_size": 0.1},
            )
        )
        signals = await strategy.run(context)
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_mean_reversion(self, context):
        strategy = MeanReversionStrategy(
            StrategyParams(
                name="mr_test",
                symbols=["BTC/USDT"],
                parameters={
                    "lookback": 20,
                    "entry_zscore": 2.0,
                    "exit_zscore": 0.5,
                    "position_size": 0.1,
                },
            )
        )
        signals = await strategy.run(context)
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_rsi_strategy(self, context):
        strategy = RSIStrategy(
            StrategyParams(
                name="rsi_test",
                symbols=["BTC/USDT"],
                parameters={"period": 14, "overbought": 70, "oversold": 30, "position_size": 0.1},
            )
        )
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
        df = pd.DataFrame(
            {
                "open": close + np.random.randn(200) * 10,
                "high": close + np.abs(np.random.randn(200) * 50),
                "low": close - np.abs(np.random.randn(200) * 50),
                "close": close,
                "volume": np.random.rand(200) * 100,
            },
            index=dates,
        )
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
        strategy = SMACrossoverStrategy(
            StrategyParams(
                name="sma_test",
                symbols=["BTC/USDT"],
                parameters={"fast_period": 10, "slow_period": 30, "position_size": 0.1},
            )
        )
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


class TestWalkForwardAnalyzer:
    @pytest.fixture
    def sample_market_data(self):
        dates = pd.date_range("2024-01-01", periods=300, freq="1h")
        np.random.seed(42)
        trend = np.linspace(0, 5000, 300)
        noise = np.cumsum(np.random.randn(300) * 100)
        close = 50000 + trend + noise
        df = pd.DataFrame(
            {
                "open": close + np.random.randn(300) * 10,
                "high": close + np.abs(np.random.randn(300) * 50),
                "low": close - np.abs(np.random.randn(300) * 50),
                "close": close,
                "volume": np.random.rand(300) * 100,
            },
            index=dates,
        )
        return {"BTC/USDT": df}

    def test_walkforward_analyzer_initialization(self):
        analyzer = WalkForwardAnalyzer(
            SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
        )
        assert analyzer.strategy_class == SMACrossoverStrategy
        assert len(analyzer.param_grid) == 2

    def test_generate_param_combinations(self):
        analyzer = WalkForwardAnalyzer(
            SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
        )
        combinations = analyzer.generate_param_combinations()
        assert len(combinations) == 4
        assert {"fast_period": 5, "slow_period": 20} in combinations
        assert {"fast_period": 10, "slow_period": 30} in combinations

    def test_create_windows(self, sample_market_data):
        analyzer = WalkForwardAnalyzer(
            SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
        )
        windows = analyzer.create_windows(
            sample_market_data,
            train_window_size=100,
            test_window_size=50,
            step_size=50,
        )
        assert len(windows) > 0
        for window in windows:
            assert window.train_start < window.train_end
            assert window.test_start > window.train_end
            assert window.test_end > window.test_start
            assert "BTC/USDT" in window.train_data
            assert "BTC/USDT" in window.test_data

    def test_run_walkforward(self, sample_market_data):
        analyzer = WalkForwardAnalyzer(
            SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
            initial_capital=100000,
        )
        strategy_params = StrategyParams(
            name="sma_test",
            symbols=["BTC/USDT"],
            parameters={"position_size": 0.1},
        )
        summary = analyzer.run_walkforward(
            sample_market_data,
            strategy_params,
            train_window_size=100,
            test_window_size=50,
            step_size=50,
        )
        assert summary.total_windows > 0
        assert len(summary.results) == summary.total_windows
        assert isinstance(summary.aggregate_train_return, float)
        assert isinstance(summary.aggregate_test_return, float)
        assert isinstance(summary.aggregate_train_sharpe, float)
        assert isinstance(summary.aggregate_test_sharpe, float)
        assert isinstance(summary.parameter_stability, dict)

    def test_run_anchored_walkforward(self, sample_market_data):
        analyzer = WalkForwardAnalyzer(
            SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
            initial_capital=100000,
        )
        strategy_params = StrategyParams(
            name="sma_test",
            symbols=["BTC/USDT"],
            parameters={"position_size": 0.1},
        )
        summary = analyzer.run_anchored_walkforward(
            sample_market_data,
            strategy_params,
            initial_train_size=100,
            test_window_size=50,
            step_size=50,
        )
        assert summary.total_windows > 0
        assert len(summary.results) == summary.total_windows
        for result in summary.results:
            assert result.train_start == summary.results[0].train_start
            assert result.best_params is not None


class TestPaperTradingEngine:
    @pytest.mark.asyncio
    async def test_paper_engine_market_order(self):
        config = PaperTradingConfig()
        engine = PaperTradingEngine(config)
        engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="paper_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        report = await engine.submit_order(order)
        assert report["status"] == OrderStatus.FILLED
        assert report["filled_quantity"] == Decimal("0.1")
        assert engine.get_balance("BTC") > Decimal("0")
        assert engine.get_balance("USDT") < Decimal("100000")

    @pytest.mark.asyncio
    async def test_paper_engine_limit_order(self):
        config = PaperTradingConfig()
        engine = PaperTradingEngine(config)
        engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="paper_2",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("49000"),
        )

        report = await engine.submit_order(order)
        assert report["status"] == OrderStatus.OPEN

        engine.update_price("BTC/USDT", Decimal("48000"))
        report = await engine.submit_order(order)
        assert report["status"] == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_paper_engine_cancel_order(self):
        config = PaperTradingConfig()
        engine = PaperTradingEngine(config)
        engine.update_price("BTC/USDT", Decimal("50000"))

        order = Order(
            id="paper_3",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("49000"),
        )

        report = await engine.submit_order(order)
        assert report["status"] == OrderStatus.OPEN

        cancelled = await engine.cancel_order("paper_3")
        assert cancelled

        status = await engine.get_order_status("paper_3")
        assert status["status"] == OrderStatus.CANCELLED

    def test_paper_engine_order_book(self):
        config = PaperTradingConfig()
        engine = PaperTradingEngine(config)
        engine.update_market_data(
            "BTC/USDT",
            bids=[(Decimal("49999"), Decimal("1")), (Decimal("49998"), Decimal("2"))],
            asks=[(Decimal("50001"), Decimal("1")), (Decimal("50002"), Decimal("2"))],
        )

        book = engine.get_order_book("BTC/USDT")
        assert book["spread"] == Decimal("2")
        assert book["mid_price"] == Decimal("50000")
        assert len(book["bids"]) == 2
        assert len(book["asks"]) == 2
        assert book["bids"][0][0] == Decimal("49999")
        assert book["asks"][0][0] == Decimal("50001")


class TestOrderManagementSystem:
    @pytest.fixture
    def oms(self, tmp_path):
        db_path = str(tmp_path / "test_oms.db")
        return OrderManager(db_path)

    @pytest.mark.asyncio
    async def test_oms_create_order(self, oms):
        order = await oms.create_order(
            client_order_id="client_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            strategy_id="strat_1",
        )
        assert order.client_order_id == "client_1"
        assert order.symbol == "BTC/USDT"
        assert order.state == OMSOrderState.CREATED
        assert len(order.events) == 1

    @pytest.mark.asyncio
    async def test_oms_validate_order(self, oms):
        order = await oms.create_order(
            client_order_id="client_2",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )

        valid = await oms.validate_order(order.order_id)
        assert valid
        assert order.state == OMSOrderState.VALIDATED

    @pytest.mark.asyncio
    async def test_oms_reject_invalid_order(self, oms):
        order = await oms.create_order(
            client_order_id="client_3",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=None,
        )

        valid = await oms.validate_order(order.order_id)
        assert not valid
        assert order.state == OMSOrderState.REJECTED

    @pytest.mark.asyncio
    async def test_oms_order_lifecycle(self, oms):
        order = await oms.create_order(
            client_order_id="client_4",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        await oms.validate_order(order.order_id)
        await oms.route_order(order.order_id, "binance")
        await oms.submit_order(order.order_id, "exch_123")
        await oms.acknowledge_order(order.order_id, "exch_123")
        await oms.update_fill(order.order_id, Decimal("0.1"), Decimal("50000"), Decimal("5"))

        assert order.state == OMSOrderState.FILLED
        assert order.filled_quantity == Decimal("0.1")
        assert order.average_fill_price == Decimal("50000")
        assert len(order.events) == 6

    @pytest.mark.asyncio
    async def test_oms_partial_fill(self, oms):
        order = await oms.create_order(
            client_order_id="client_5",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
        )

        await oms.validate_order(order.order_id)
        await oms.route_order(order.order_id, "binance")
        await oms.submit_order(order.order_id, "exch_123")
        await oms.acknowledge_order(order.order_id, "exch_123")

        await oms.update_fill(order.order_id, Decimal("0.3"), Decimal("50000"), Decimal("15"))
        assert order.state == OMSOrderState.PARTIAL_FILL
        assert order.filled_quantity == Decimal("0.3")

        await oms.update_fill(order.order_id, Decimal("0.7"), Decimal("50100"), Decimal("35"))
        assert order.state == OMSOrderState.FILLED
        assert order.filled_quantity == Decimal("1.0")


class TestSmartOrderRouter:
    @pytest.fixture
    def router(self):
        config = SmartOrderRouterConfig(
            venue_configs={
                "binance": VenueConfig(
                    name="binance",
                    venue_type=VenueType.EXCHANGE,
                    fee_rate=Decimal("0.001"),
                    priority=10,
                ),
                "bybit": VenueConfig(
                    name="bybit",
                    venue_type=VenueType.EXCHANGE,
                    fee_rate=Decimal("0.0015"),
                    priority=20,
                ),
            }
        )
        router = SmartOrderRouter(config)
        return router

    def test_router_add_venue(self, router):
        assert "binance" in router.venues
        assert "bybit" in router.venues
        assert router.venue_configs["binance"].fee_rate == Decimal("0.001")

    def test_router_update_quote(self, router):
        router.update_venue_quote("binance", "BTC/USDT", Decimal("49999"), Decimal("50001"), Decimal("10"), Decimal("10"))
        router.update_venue_quote("bybit", "BTC/USDT", Decimal("49998"), Decimal("50002"), Decimal("5"), Decimal("5"))

        best_buy = router.get_best_quote("BTC/USDT", OrderSide.BUY)
        assert best_buy is not None
        assert best_buy.venue == "binance"
        assert best_buy.ask == Decimal("50001")

        best_sell = router.get_best_quote("BTC/USDT", OrderSide.SELL)
        assert best_sell is not None
        assert best_sell.venue == "binance"
        assert best_sell.bid == Decimal("49999")

    @pytest.mark.asyncio
    async def test_router_best_price_strategy(self, router):
        await router.connect_all()

        router.update_venue_quote("binance", "BTC/USDT", Decimal("49999"), Decimal("50001"), Decimal("10"), Decimal("10"))
        router.update_venue_quote("bybit", "BTC/USDT", Decimal("49998"), Decimal("50002"), Decimal("5"), Decimal("5"))

        order = Order(
            id="sor_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        decisions = router.calculate_routing(order, RoutingStrategy.BEST_PRICE)
        assert len(decisions) == 1
        assert decisions[0].venue == "binance"

    @pytest.mark.asyncio
    async def test_router_pro_rata_strategy(self, router):
        await router.connect_all()

        router.update_venue_quote("binance", "BTC/USDT", Decimal("49999"), Decimal("50001"), Decimal("10"), Decimal("10"))
        router.update_venue_quote("bybit", "BTC/USDT", Decimal("49998"), Decimal("50002"), Decimal("5"), Decimal("5"))

        order = Order(
            id="sor_2",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
        )

        decisions = router.calculate_routing(order, RoutingStrategy.PRO_RATA)
        assert len(decisions) == 2
        total_qty = sum(d.quantity for d in decisions)
        assert abs(total_qty - Decimal("1.0")) < Decimal("0.01")


class TestExecutionAlgorithms:
    @pytest.fixture
    def router(self):
        config = SmartOrderRouterConfig(
            venue_configs={
                "binance": VenueConfig(name="binance", fee_rate=Decimal("0.001")),
            }
        )
        router = SmartOrderRouter(config)
        return router

    @pytest.fixture
    def algo_config(self):
        return ExecutionAlgorithmConfig(
            algorithm_type=AlgorithmType.TWAP,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("1.0"),
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=10),
            num_slices=5,
            limit_price=Decimal("50000"),
        )

    def test_twap_generate_slices(self, router, algo_config):
        algo = TWAPAlgorithm(algo_config, router)
        slices = algo.generate_slices()
        assert len(slices) == 5
        total = sum(s.quantity for s in slices)
        assert abs(total - Decimal("1.0")) < Decimal("0.01")

    def test_vwap_generate_slices(self, router):
        now = datetime.now()
        volume_profile = [
            (now + timedelta(minutes=i), Decimal("100") * (i + 1))
            for i in range(10)
        ]
        config = ExecutionAlgorithmConfig(
            algorithm_type=AlgorithmType.VWAP,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("1.0"),
            start_time=now,
            end_time=now + timedelta(minutes=11),
            limit_price=Decimal("50000"),
        )
        algo = VWAPAlgorithm(config, router, volume_profile=volume_profile)
        slices = algo.generate_slices()
        assert len(slices) == 10
        total = sum(s.quantity for s in slices)
        assert abs(total - Decimal("1.0")) < Decimal("0.01")

    def test_pov_generate_slices(self, router, algo_config):
        algo = POVAlgorithm(algo_config, router)
        slices = algo.generate_slices()
        assert len(slices) > 0

    def test_implementation_shortfall_generate_slices(self, router):
        config = ExecutionAlgorithmConfig(
            algorithm_type=AlgorithmType.IMPLEMENTATION_SHORTFALL,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("1.0"),
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=10),
            urgency=Decimal("1.0"),
            num_slices=5,
        )
        algo = ImplementationShortfallAlgorithm(config, router)
        slices = algo.generate_slices()
        assert len(slices) == 5
        total = sum(s.quantity for s in slices)
        assert abs(total - Decimal("1.0")) < Decimal("0.01")

    def test_algorithm_factory(self, router, algo_config):
        twap = AlgorithmFactory.create(AlgorithmType.TWAP, algo_config, router)
        assert isinstance(twap, TWAPAlgorithm)

        vwap = AlgorithmFactory.create(AlgorithmType.VWAP, algo_config, router, volume_profile=[])
        assert isinstance(vwap, VWAPAlgorithm)

        pov = AlgorithmFactory.create(AlgorithmType.POV, algo_config, router)
        assert isinstance(pov, POVAlgorithm)

        is_algo = AlgorithmFactory.create(AlgorithmType.IMPLEMENTATION_SHORTFALL, algo_config, router)
        assert isinstance(is_algo, ImplementationShortfallAlgorithm)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
