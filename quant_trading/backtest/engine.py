"""Backtest engine for strategy validation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal, Strategy


@dataclass
class Trade:
    """Represents a single trade."""

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
        """Total cost including commission and slippage."""
        base = self.quantity * self.price
        if self.action == "buy":
            return base * (1 + self.commission + self.slippage)
        else:
            return base * (1 - self.commission - self.slippage)

    @property
    def pnl(self) -> float:
        """Realized PnL for this trade (0.0 for opens, set on closes)."""
        return self.realized_pnl


@dataclass
class BacktestResult:
    """Result of a backtest run."""

    equity_curve: pd.Series
    trades: pd.DataFrame
    positions: dict[str, Any]
    metrics: Any  # BacktestMetrics
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_value: float
    total_return: float
    total_return_pct: float


class BacktestEngine:
    """Engine for running backtests on trading strategies."""

    def __init__(
        self,
        config: BacktestConfig | None = None,
        data_manager: DataManager | None = None,
        risk_manager: RiskManager | None = None,
    ):
        self.config = config or BacktestConfig()
        self.data_manager = data_manager
        self.risk_manager = risk_manager or RiskManager(
            initial_capital=self.config.initial_capital,
        )
        self.portfolio = Portfolio(cash=self.config.initial_capital)
        self.strategies: dict[str, Strategy] = {}

    def add_strategy(self, strategy: Strategy) -> None:
        """Add a strategy to the backtest."""
        self.strategies[strategy.name] = strategy

    def remove_strategy(self, name: str) -> None:
        """Remove a strategy from the backtest."""
        self.strategies.pop(name, None)

    def run(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> BacktestResult:
        """Run backtest for given symbols and date range.

        Requires an explicit data_manager to be set on the engine.
        Raises ValueError if no data_manager is configured.
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
        trades_list: list[Trade] = []
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

            # Update risk manager
            self.risk_manager.update_portfolio_value(
                self.portfolio.get_positions(),
                self.portfolio.cash,
            )

        # Create result
        equity_series = pd.Series(equity_curve, index=[start] + list(dates))
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
        data_manager: Optional DataManager for offline/testing. If not provided,
            a live YFinanceProvider will be used (requires network).
    """
    config = BacktestConfig(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )
    if data_manager is None:
        from quant_trading.data.yfinance_provider import YFinanceProvider

        data_manager = DataManager([YFinanceProvider()])
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(strategy)
    return engine.run(symbols, start, end, interval)
