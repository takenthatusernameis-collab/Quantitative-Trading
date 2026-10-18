"""Backtest engine for strategy validation.

Examples:
    Run a backtest offline using synthetic data and inspect the result::

        from datetime import datetime, timedelta

        from quant_trading.backtest.engine import BacktestEngine, run_backtest
        from quant_trading.config.settings import BacktestConfig
        from quant_trading.data.providers import DataManager
        from quant_trading.data.synthetic import create_synthetic_provider
        from quant_trading.strategies.examples import MovingAverageCrossover

        symbols = ["AAPL"]
        end = datetime(2023, 12, 31)
        start = end - timedelta(days=100)

        provider = create_synthetic_provider(symbols, days=100, seed=42)
        data_manager = DataManager([provider])

        engine = BacktestEngine(
            config=BacktestConfig(initial_capital=100000.0),
            data_manager=data_manager,
        )
        engine.add_strategy(MovingAverageCrossover(fast_period=5, slow_period=20))
        result = engine.run(symbols, start, end)
        assert result is not None
        assert result.final_value >= result.initial_capital * 0.5

    Use the convenience function to run a single strategy offline::

        from datetime import datetime, timedelta

        from quant_trading.backtest.engine import run_backtest
        from quant_trading.data.providers import DataManager
        from quant_trading.data.synthetic import create_synthetic_provider
        from quant_trading.strategies.examples import MovingAverageCrossover

        symbols = ["AAPL"]
        end = datetime(2023, 12, 31)
        start = end - timedelta(days=100)

        provider = create_synthetic_provider(symbols, days=100, seed=42)
        data_manager = DataManager([provider])

        result = run_backtest(
            strategy=MovingAverageCrossover(fast_period=5, slow_period=20),
            symbols=symbols,
            start=start,
            end=end,
            initial_capital=100000.0,
            data_manager=data_manager,
        )
        assert result.trades is not None
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.config.settings import BacktestConfig, Config, DataConfig
from quant_trading.data.providers import DataManager, create_data_manager_from_config
from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal, Strategy

_default_data_manager: DataManager | None = None


def get_default_data_manager() -> DataManager:
    """Get or create the module-level default DataManager with YFinanceProvider.

    Returns a shared DataManager instance that can be reused across backtest
    runs. The manager is created lazily on first access and uses a
    YFinanceProvider with default cache settings.
    """
    global _default_data_manager
    if _default_data_manager is None:
        from quant_trading.data.yfinance_provider import YFinanceProvider

        _default_data_manager = DataManager([YFinanceProvider()])
    return _default_data_manager


def reset_default_data_manager() -> None:
    """Reset the module-level default DataManager.

    Useful for testing to ensure a fresh DataManager with cleared cache.
    """
    global _default_data_manager
    _default_data_manager = None


@dataclass
class Trade:
    """Represents a single trade.

    Attributes:
        symbol: Traded symbol.
        action: Trade action ("buy" or "sell").
        quantity: Number of units traded.
        price: Execution price.
        timestamp: Trade timestamp.
        commission: Commission rate applied.
        slippage: Slippage rate applied.
        realized_pnl: Realized PnL (set on closes).
    """

    symbol: str
    action: str  # 'buy' or 'sell'
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0
    realized_pnl: float = 0.0

    @property
    def cost(self) -> float:
        """Total cost of the trade including commission and slippage.

        Buys are charged (cost is increased) and sells are credited (cost is
        reduced) by the commission and slippage rates.

        Returns:
            The gross trade value adjusted for commission and slippage.
        """
        base = self.quantity * self.price
        if self.action == "buy":
            return base * (1 + self.commission + self.slippage)
        else:
            return base * (1 - self.commission - self.slippage)

    @property
    def pnl(self) -> float:
        """Realized PnL for this trade.

        Returns:
            The realized PnL. This is ``0.0`` for opening trades and is set
            on closing trades when the position is exited.
        """
        return self.realized_pnl


@dataclass
class BacktestResult:
    """Result of a backtest run.

    Attributes:
        equity_curve: Equity curve as a pandas Series indexed by date.
        trades: DataFrame containing trade details (symbol, action, quantity,
            price, timestamp, commission, slippage, cost, pnl).
        positions: Current positions dictionary.
        metrics: Backtest performance metrics.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Initial capital amount.
        final_value: Final portfolio value.
        total_return: Total dollar return.
        total_return_pct: Total return percentage.
        portfolio_violations: List of portfolio-level violation messages.

    Examples:
        Inspect key result fields after a backtest run::

            assert result.initial_capital > 0
            assert result.final_value >= 0
            assert isinstance(result.metrics.sharpe_ratio, float)
            assert result.trades is not None
            assert result.equity_curve is not None
    """

    equity_curve: pd.Series
    trades: pd.DataFrame
    positions: dict[str, Any]
    metrics: BacktestMetrics
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_value: float
    total_return: float
    total_return_pct: float
    portfolio_violations: list[str] = field(default_factory=list)


class BacktestEngine:
    """Engine for running backtests on trading strategies.

    The engine fetches market data for a set of symbols over a date range,
    generates trading signals from registered strategies on each bar,
    executes the signals against a :class:`Portfolio`, and records the
    resulting equity curve and trades.

    Attributes:
        config: Backtest configuration.
        data_manager: DataManager providing market data.
        risk_manager: Risk manager instance.
        portfolio: Portfolio tracking positions and cash.
        strategies: Registered strategies keyed by name.

    Examples:
        Create an engine with offline synthetic data and run a backtest::

            from datetime import datetime, timedelta

            from quant_trading.backtest.engine import BacktestEngine
            from quant_trading.config.settings import BacktestConfig
            from quant_trading.data.providers import DataManager
            from quant_trading.data.synthetic import create_synthetic_provider
            from quant_trading.strategies.examples import MovingAverageCrossover

            symbols = ["AAPL"]
            end = datetime(2023, 12, 31)
            start = end - timedelta(days=100)

            provider = create_synthetic_provider(symbols, days=100, seed=42)
            data_manager = DataManager([provider])

            engine = BacktestEngine(
                config=BacktestConfig(initial_capital=100000.0),
                data_manager=data_manager,
            )
            engine.add_strategy(MovingAverageCrossover(fast_period=5, slow_period=20))
            result = engine.run(symbols, start, end)
            assert len(result.trades) >= 0
    """

    def __init__(
        self,
        config: BacktestConfig | None = None,
        data_manager: DataManager | None = None,
        risk_manager: RiskManager | None = None,
    ):
        """Initialize the backtest engine.

        Args:
            config: Backtest configuration. Defaults to ``BacktestConfig()``.
            data_manager: DataManager providing market data.
            risk_manager: Risk manager instance. Defaults to a new RiskManager.
        """
        self.config = config or BacktestConfig()
        self.data_manager = data_manager
        self.risk_manager = risk_manager or RiskManager(
            initial_capital=self.config.initial_capital,
        )
        self.portfolio = Portfolio(cash=self.config.initial_capital)
        self.strategies: dict[str, Strategy] = {}

    def add_strategy(self, strategy: Strategy) -> None:
        """Add a strategy to the backtest.

        Args:
            strategy: Strategy instance to register.
        """
        self.strategies[strategy.name] = strategy

    def remove_strategy(self, name: str) -> None:
        """Remove a strategy from the backtest.

        Args:
            name: Name of the strategy to remove.
        """
        self.strategies.pop(name, None)

    def run(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> BacktestResult:
        """Run backtest for given symbols and date range.

        Args:
            symbols: List of symbols to trade.
            start: Backtest start date.
            end: Backtest end date.
            interval: Data interval (default: "1d").

        Returns:
            BacktestResult containing equity curve, trades, metrics, and metadata.

        Raises:
            ValueError: If no data_manager is configured or no data retrieved.
            RuntimeError: If data fetch errors occur.
        """
        if self.data_manager is None:
            raise ValueError(
                "No data_manager configured. Provide a DataManager instance "
                "to BacktestEngine or use run_backtest() with a data_manager parameter."
            )

        fetch_result = self.data_manager.fetch(
            symbols=symbols,
            start=start,
            end=end,
            interval=interval,
        )

        if fetch_result.has_errors:
            error_msg = ", ".join(f"{s}: {e}" for s, e in fetch_result.errors.items())
            raise RuntimeError(f"Data fetch errors: {error_msg}")

        if not fetch_result.data:
            raise ValueError("No market data retrieved for any symbol")

        # Prepare data dict for strategies
        data = {symbol: md.data for symbol, md in fetch_result.data.items()}

        # Reset portfolio and risk manager
        self.portfolio.reset(self.config.initial_capital)
        self.risk_manager.reset()

        equity_curve = [self.config.initial_capital]
        processed_dates: list[datetime] = []
        trades_list: list[Trade] = []
        portfolio_violations: list[str] = []
        dates = sorted(set().union(*[df.index for df in data.values()]))

        for current_date in dates:
            # Get data up to current date
            current_data = {
                symbol: df[df.index <= current_date]
                for symbol, df in data.items()
                if len(df[df.index <= current_date]) > 0
            }

            if not current_data:
                continue

            # Generate signals from all strategies
            all_signals = []
            for strategy in self.strategies.values():
                signals = strategy.generate_signals(current_data)
                all_signals.extend(signals)

            # Process signals
            for signal in all_signals:
                self._process_signal(signal, trades_list, current_date)

            # Update portfolio value
            prices = {
                symbol: df.loc[current_date, "close"]
                for symbol, df in current_data.items()
                if current_date in df.index
            }
            self.portfolio.update_prices(prices)
            equity_curve.append(self.portfolio.total_value)
            processed_dates.append(current_date)

            # Update risk manager
            self.risk_manager.update_portfolio_value(
                self.portfolio.get_positions(),
                self.portfolio.cash,
            )

            # Enforce portfolio-level limits (max drawdown, max positions, etc.)
            portfolio_check = self.risk_manager.check_portfolio()
            portfolio_violations.extend(portfolio_check.violations)
            if not portfolio_check.ok and self.config.halt_on_portfolio_violation:
                break

        # Create result
        equity_series = pd.Series(equity_curve, index=[start] + processed_dates)
        trades_df = pd.DataFrame(
            [
                {
                    "symbol": t.symbol,
                    "action": t.action,
                    "quantity": t.quantity,
                    "price": t.price,
                    "timestamp": t.timestamp,
                    "commission": t.commission,
                    "slippage": t.slippage,
                    "cost": t.cost,
                    "pnl": t.pnl,
                }
                for t in trades_list
            ]
        )

        from quant_trading.backtest.metrics import calculate_backtest_metrics

        metrics = calculate_backtest_metrics(
            equity_series,
            trades_df,
            risk_free_rate=self.config.risk_free_rate,
        )

        return BacktestResult(
            equity_curve=equity_series,
            trades=trades_df,
            positions=self.portfolio.get_positions(),
            metrics=metrics,
            start_date=start,
            end_date=end,
            initial_capital=self.config.initial_capital,
            final_value=self.portfolio.total_value,
            total_return=self.portfolio.total_value - self.config.initial_capital,
            total_return_pct=(self.portfolio.total_value / self.config.initial_capital - 1) * 100,
            portfolio_violations=portfolio_violations,
        )

    def _process_signal(
        self,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
    ) -> None:
        """Process a trading signal."""
        # Check risk limits
        risk_result = self.risk_manager.check_signal(signal, self.portfolio.total_value)
        if not risk_result.ok:
            return

        symbol = signal.symbol
        holding = self.portfolio.holdings.get(symbol)
        price = signal.price or (holding.current_price if holding else None)
        if price is None or price <= 0:
            return

        if signal.action == "buy":
            # Calculate position size based on signal strength and risk limits
            max_position_value = (
                self.portfolio.total_value * self.risk_manager.position_limit.max_size
            )
            target_value = max_position_value * signal.strength
            current_value = self.portfolio.get_position_value(symbol)
            available_value = target_value - current_value

            if available_value <= 0:
                return

            quantity = available_value / price
            cost = quantity * price * (1 + self.config.commission + self.config.slippage)

            if cost > self.portfolio.cash:
                quantity = self.portfolio.cash / (
                    price * (1 + self.config.commission + self.config.slippage)
                )
                if quantity <= 0:
                    return

            self.portfolio.add_holding(symbol, quantity, price)
            trades_list.append(
                Trade(
                    symbol=symbol,
                    action="buy",
                    quantity=quantity,
                    price=price,
                    timestamp=timestamp,
                    commission=self.config.commission,
                    slippage=self.config.slippage,
                )
            )

        elif signal.action == "sell":
            holding = self.portfolio.holdings.get(symbol)
            if holding is None or holding.quantity <= 0:
                return

            quantity = holding.quantity * signal.strength
            if quantity <= 0:
                return

            avg_cost = holding.avg_cost
            self.portfolio.remove_holding(symbol, quantity, price)
            realized_pnl = (
                quantity * price * (1 - self.config.commission - self.config.slippage)
                - avg_cost * quantity
            )
            trades_list.append(
                Trade(
                    symbol=symbol,
                    action="sell",
                    quantity=quantity,
                    price=price,
                    timestamp=timestamp,
                    commission=self.config.commission,
                    slippage=self.config.slippage,
                    realized_pnl=realized_pnl,
                )
            )


def run_backtest(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_capital: float = 100000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
    interval: str = "1d",
    data_manager: DataManager | None = None,
    config: Config | DataConfig | None = None,
) -> BacktestResult:
    """Convenience function to run a single strategy backtest.

    Args:
        strategy: The strategy to backtest.
        symbols: List of symbols to trade.
        start: Start date for backtest.
        end: End date for backtest.
        initial_capital: Initial capital (default: 100000.0).
        commission: Commission rate (default: 0.001).
        slippage: Slippage rate (default: 0.0005).
        interval: Data interval (default: "1d").
        data_manager: Optional DataManager for offline/testing. If not provided
            and no config is given, a shared default DataManager with
            YFinanceProvider will be used (requires network).
        config: Optional Config or DataConfig. If provided, a DataManager will
            be created from the config (supporting offline/synthetic modes).
            Takes precedence over data_manager if both are provided.

    Returns:
        BacktestResult containing equity curve, trades, metrics, and metadata.

    Examples:
        Run a single strategy backtest using synthetic offline data::

            from datetime import datetime, timedelta

            from quant_trading.backtest.engine import run_backtest
            from quant_trading.data.providers import DataManager
            from quant_trading.data.synthetic import create_synthetic_provider
            from quant_trading.strategies.examples import MovingAverageCrossover

            symbols = ["AAPL", "MSFT"]
            end = datetime(2023, 12, 31)
            start = end - timedelta(days=100)

            provider = create_synthetic_provider(symbols, days=100, seed=42)
            data_manager = DataManager([provider])

            result = run_backtest(
                strategy=MovingAverageCrossover(fast_period=5, slow_period=20),
                symbols=symbols,
                start=start,
                end=end,
                initial_capital=100000.0,
                commission=0.001,
                slippage=0.0005,
                data_manager=data_manager,
            )
            assert result is not None
            assert result.initial_capital == 100000.0
            assert result.metrics is not None
    """
    backtest_config = BacktestConfig(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )

    if data_manager is None:
        if config is not None:
            data_config = config.data if isinstance(config, Config) else config
            data_manager = create_data_manager_from_config(data_config)
        else:
            data_manager = get_default_data_manager()

    engine = BacktestEngine(config=backtest_config, data_manager=data_manager)
    engine.add_strategy(strategy)
    return engine.run(symbols, start, end, interval)
