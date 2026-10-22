"""Backtest engine for strategy validation.

The engine fetches market data for a set of symbols over a date range,
generates trading signals from registered strategies on each bar, executes
the signals against a :class:`~quant_trading.portfolio.portfolio.Portfolio`,
and records the resulting equity curve and trades. It is the core entry
point for offline backtesting and is exercised by the test suite with
synthetic data so that no network access is required.

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

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)
from quant_trading.data.providers import DataManager, create_data_manager_from_config
from quant_trading.portfolio.portfolio import Holding, Portfolio
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal, Strategy

_default_data_manager: DataManager | None = None


def get_default_data_manager() -> DataManager:
    """Get or create the module-level default DataManager with YFinanceProvider.

    Returns a shared DataManager instance that can be reused across backtest
    runs. The manager is created lazily on first access and uses a
    YFinanceProvider with default cache settings.

    Returns:
        The shared default :class:`~quant_trading.data.providers.DataManager`
        instance.

    """
    global _default_data_manager
    if _default_data_manager is None:
        from quant_trading.data.yfinance_provider import YFinanceProvider

        _default_data_manager = DataManager([YFinanceProvider()])
    return _default_data_manager


def reset_default_data_manager() -> None:
    """Reset the module-level default DataManager.

    Useful for testing to ensure a fresh DataManager with cleared cache.

    Returns:
        None.

    """
    global _default_data_manager
    _default_data_manager = None


@dataclass
class Trade:
    """Represents a single trade.

    Attributes:
        symbol: Traded symbol.
        action: Trade action ("buy", "sell", "short", or "cover"). A "buy"
            opens or adds to a long position, a "sell" reduces or closes one,
            a "short" opens or adds to a short position, and a "cover" reduces
            or closes one.
        quantity: Number of units traded. It is always positive; the action
            says which way the trade went.
        price: Execution price.
        timestamp: Trade timestamp.
        commission: Commission rate applied.
        slippage: Slippage rate applied.
        realized_pnl: Realized PnL. It is 0.0 when a position is opened and
            holds the PnL of the closed part when a position is reduced. A
            short entry books the entry fee it paid, because a short keeps
            the raw execution price as its cost basis.

    """

    symbol: str
    action: str  # 'buy', 'sell', 'short', 'cover'
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0
    realized_pnl: float = 0.0

    @property
    def cost(self) -> float:
        """Total cost of the trade including commission and slippage.

        Buys and covers are charged (cost is increased) and sells and shorts
        are credited (cost is reduced) by the commission and slippage rates.

        Returns:
            The gross trade value adjusted for commission and slippage.

        """
        base = self.quantity * self.price
        if self.action in ("buy", "cover"):
            return base * (1 + self.commission + self.slippage)
        else:
            return base * (1 - self.commission - self.slippage)

    @property
    def fee(self) -> float:
        """Total commission and slippage charged for this trade.

        The fee is always paid on the gross trade value, so it is positive
        for both buys and sells.

        Returns:
            ``quantity * price * (commission + slippage)``.

        Examples:
            Compute the fee charged on a round-trip trade::

                from datetime import datetime

                from quant_trading.backtest.engine import Trade

                buy = Trade(
                    symbol="AAPL",
                    action="buy",
                    quantity=100,
                    price=150.0,
                    timestamp=datetime.now(),
                    commission=0.001,
                    slippage=0.0005,
                )
                assert buy.fee == 22.5

        """
        return self.quantity * self.price * (self.commission + self.slippage)

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
            price, timestamp, commission, slippage, cost, fee, pnl).
        positions: Current positions dictionary.
        metrics: Backtest performance metrics.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Initial capital amount.
        final_value: Final portfolio value.
        total_return: Total dollar return.
        total_return_pct: Total return percentage.
        portfolio_violations: List of portfolio-level violation messages.
        total_costs: Total commission and slippage paid over the run. It is
            the sum of the per-trade fees, i.e. ``quantity * price *
            (commission + slippage)`` for every executed trade.

    The headline numbers reconcile against the trade log as follows:

    - ``final_value - initial_capital`` equals the sum of the signed
      ``Trade.cost`` values (buys and covers reduce cash, sells and shorts
      increase it), because commission and slippage are charged to cash on
      both sides.
    - Entry fees are capitalized into the position's cost basis
      (``Holding.avg_cost``), so realized PnL is net of both buy-side and
      sell-side fees. For a fully liquidated round trip,
      ``final_value - initial_capital == sum(Trade.pnl)``; with open
      positions remaining, realized PnL excludes the basis of unsold shares.
    - A short keeps the raw execution price as its cost basis, so the entry
      fee it pays is booked as realized PnL on the short trade itself and the
      cover books the price move and the cover fee. A fully liquidated short
      round trip therefore reconciles the same way.
    - The buy-side share of costs is
      ``trades[trades["action"] == "buy"]["fee"].sum()`` and the sell-side
      share is the remainder of ``total_costs``.

    Examples:
        Inspect key result fields after a backtest run::

            assert result.initial_capital > 0
            assert result.final_value >= 0
            assert isinstance(result.metrics.sharpe_ratio, float)
            assert result.trades is not None
            assert result.equity_curve is not None
            assert result.total_costs >= 0

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
    total_costs: float = 0.0


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
        config: BacktestConfig | Config | None = None,
        data_manager: DataManager | None = None,
        risk_manager: RiskManager | None = None,
    ):
        """Initialize the backtest engine.

        Args:
            config: Backtest configuration or a full :class:`Config`. When a
                full ``Config`` is supplied, its ``risk`` and ``portfolio``
                sub-configs drive the default :class:`RiskManager`; when only a
                ``BacktestConfig`` is supplied, the risk/portfolio defaults are
                used. Defaults to ``BacktestConfig()``.
            data_manager: DataManager providing market data.
            risk_manager: Risk manager instance. Defaults to a new RiskManager.

        """
        if config is None:
            config = BacktestConfig()
        if isinstance(config, Config):
            backtest_cfg = config.backtest
            risk_cfg = config.risk
            portfolio_cfg = config.portfolio
        else:
            backtest_cfg = config
            risk_cfg = RiskConfig()
            portfolio_cfg = PortfolioConfig()
        self.config = backtest_cfg
        self.data_manager = data_manager

        self.risk_manager = risk_manager or RiskManager(
            initial_capital=backtest_cfg.initial_capital,
            max_position_size=risk_cfg.max_position_size,
            max_portfolio_risk=risk_cfg.max_portfolio_risk,
            max_leverage=risk_cfg.max_leverage,
            stop_loss_pct=risk_cfg.stop_loss_pct,
            take_profit_pct=risk_cfg.take_profit_pct,
            max_drawdown=risk_cfg.max_drawdown,
            max_positions=portfolio_cfg.max_positions,
            trailing_stop_pct=risk_cfg.trailing_stop_pct,
            trailing_stop_activation_pct=risk_cfg.trailing_stop_activation_pct,
        )
        self.portfolio = Portfolio(cash=backtest_cfg.initial_capital)
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

                The bar loop generates the signals of the registered strategies,
                executes them, marks the portfolio to the bar's close and then
                refreshes the risk manager. When ``enable_stop_exits`` is set, a
                position whose bar close hit its stop loss, its take profit or its
                trailing stop is closed at that close before the bar is closed out.

                Args:
                    symbols: List of symbols to trade.
                    start: Backtest start date.
                    end: Backtest end date.
        interval: Data interval. Defaults to the configured value, or to "1d"
                    when nothing is configured.

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

            # Update risk manager
            self.risk_manager.update_portfolio_value(
                self.portfolio.get_positions(),
                self.portfolio.cash,
            )

            # Close the positions whose stop loss, take profit or trailing
            # stop was hit. This runs after the risk manager has seen the
            # bar's close, so the trailing stop is up to date before it is
            # checked.
            if self.config.enable_stop_exits:
                self._process_stop_exits(prices, trades_list, current_date)

            equity_curve.append(self.portfolio.total_value)
            processed_dates.append(current_date)

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
                    "fee": t.fee,
                    "pnl": t.pnl,
                }
                for t in trades_list
            ]
        )

        # Total commission and slippage paid across the run. It is derived from
        # the executed trades so it always matches the trade log.
        total_costs = sum(t.fee for t in trades_list)

        from quant_trading.backtest.metrics import calculate_backtest_metrics

        metrics = calculate_backtest_metrics(
            equity_series,
            trades_df,
            risk_free_rate=self.config.risk_free_rate,
            periods_per_year=self.config.periods_per_year,
        )

        initial_capital = self.config.initial_capital
        total_return_pct = (
            (self.portfolio.total_value / initial_capital - 1) * 100
            if initial_capital != 0
            else 0.0
        )

        return BacktestResult(
            equity_curve=equity_series,
            trades=trades_df,
            positions=self.portfolio.get_positions(),
            metrics=metrics,
            start_date=start,
            end_date=end,
            initial_capital=initial_capital,
            final_value=self.portfolio.total_value,
            total_return=self.portfolio.total_value - initial_capital,
            total_return_pct=total_return_pct,
            portfolio_violations=portfolio_violations,
            total_costs=total_costs,
        )

    def _process_signal(
        self,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
    ) -> None:
        """Process a single trading signal and append any resulting trades.

        The signal is first validated against the risk manager. If it is
        rejected, no trade is recorded. For buy signals the position size is
        derived from the signal strength and the configured position limit,
        trimmed to fit available cash. A buy against an open short covers
        that short instead, because a buy never flips a position. For sell
        signals the holding is sold in proportion to the signal strength,
        capped at the size of the position, and the realized PnL is recorded.
        A short signal opens a short position of the same size a buy would
        open; the sale credits its proceeds to the cash balance. A short
        against an open long is rejected, because a short never flips a
        position either: the long stays as it is and no trade is recorded.
        The risk manager rejects the same signal, so the rule holds whether
        the risk checks are enabled or not. Signals with an unrecognized
        action or insufficient price information are ignored.

        Args:
            signal: The trading signal to process.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to any trade created.

        Returns:
            None.

        """
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
            if holding is not None and holding.quantity < 0:
                # A buy against an open short covers it.
                self._cover_short(symbol, signal, trades_list, timestamp, price, holding)
            else:
                self._open_long(symbol, signal, trades_list, timestamp, price)

        elif signal.action == "sell":
            self._reduce_long(symbol, signal, trades_list, timestamp, price)

        elif signal.action == "short":
            if holding is not None and holding.quantity > 0:
                # A short never flips a position, so a short signal against an
                # open long is rejected and the long is left alone. The risk
                # manager rejects the same signal; the engine enforces the
                # rule on its own as well, so the trade log can never record a
                # short that the portfolio turned into a sale.
                return
            self._open_short(symbol, signal, trades_list, timestamp, price)

    def _process_stop_exits(
        self,
        prices: dict[str, float],
        trades_list: list[Trade],
        timestamp: datetime,
    ) -> None:
        """Close the positions whose stop or target was hit on this bar.

        Every open position is measured against the levels the risk manager
        computes for it: the stop loss (the fixed stop, or the trailing stop
        when it is the tighter one) and the take profit. A position whose bar
        close reached one of them is closed at that close, which is the price
        the engine knows on the bar: no intrabar path and no look-ahead are
        assumed.

        The stop loss is evaluated before the take profit, and the position is
        closed once, at the bar's close, whichever level was reached. A
        trailing stop can only be hit on a bar after the one that ratcheted
        it, because the stop is always placed below (above, for a short) the
        best price the position has reached.

        The exit is recorded like any other trade, so the trade log and the
        accounting stay consistent: a run that is liquidated this way still
        reconciles ``final_value - initial_capital == sum(trades["pnl"])``.

        Args:
            prices: Close price of every symbol that has a bar on this date.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to any trade created.

        Returns:
            None.

        """
        # The holdings are closed while the loop runs, so the symbols are
        # snapshotted first.
        for symbol in list(self.portfolio.holdings):
            price = prices.get(symbol)
            if price is None or price <= 0:
                # The symbol has no price on this bar, so no level can be
                # measured against it.
                continue

            holding = self.portfolio.holdings.get(symbol)
            if holding is None or holding.quantity == 0:
                continue

            stopped = self.risk_manager.should_stop_loss(symbol, price)
            targeted = self.risk_manager.should_take_profit(symbol, price)
            if not stopped and not targeted:
                continue

            if holding.quantity < 0:
                # A short is closed by buying it back.
                self._cover_short(
                    symbol,
                    Signal(symbol=symbol, action="buy", strength=1.0, price=price),
                    trades_list,
                    timestamp,
                    price,
                    holding,
                )
            else:
                self._reduce_long(
                    symbol,
                    Signal(symbol=symbol, action="sell", strength=1.0, price=price),
                    trades_list,
                    timestamp,
                    price,
                )

    def _open_long(
        self,
        symbol: str,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
        price: float,
    ) -> None:
        """Open or add to a long position.

        The position size is derived from the signal strength and the
        configured position limit, less the value the symbol already holds,
        and is trimmed to fit the available cash.

        Args:
            symbol: Symbol that is traded.
            signal: The trading signal that triggered the trade.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to the trade.
            price: Execution price of the trade.

        Returns:
            None.

        """
        # Calculate position size based on signal strength and risk limits
        max_position_value = self.portfolio.total_value * self.risk_manager.position_limit.max_size
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

        self.portfolio.add_holding(
            symbol,
            quantity,
            price,
            commission=self.config.commission,
            slippage=self.config.slippage,
        )
        # Keep the risk manager's view of the portfolio current, so a
        # later signal in this same bar is measured against the exposure
        # this trade just added instead of the exposure of the previous bar.
        self.risk_manager.sync_position(symbol, self.portfolio.get_position(symbol))
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

    def _reduce_long(
        self,
        symbol: str,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
        price: float,
    ) -> None:
        """Sell part of a long position or close it completely.

        The holding is sold in proportion to the signal strength and capped
        at the size of the position, and the realized PnL is recorded.

        Args:
            symbol: Symbol that is traded.
            signal: The trading signal that triggered the trade.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to the trade.
            price: Execution price of the trade.

        Returns:
            None.

        """
        holding = self.portfolio.holdings.get(symbol)
        if holding is None or holding.quantity <= 0:
            return

        # The portfolio caps the removal at the position size, so the
        # executed quantity is capped here as well. Otherwise a signal with
        # ``strength > 1`` would record a trade larger than the position it
        # actually closed.
        quantity = min(holding.quantity * signal.strength, holding.quantity)
        if quantity <= 0:
            return

        avg_cost = holding.avg_cost
        self.portfolio.remove_holding(
            symbol,
            quantity,
            price,
            commission=self.config.commission,
            slippage=self.config.slippage,
        )
        realized_pnl = (
            quantity * price * (1 - self.config.commission - self.config.slippage)
            - avg_cost * quantity
        )
        # The risk manager's view of the portfolio is refreshed here as
        # well, so a position closed in this bar stops counting towards
        # the exposure of the signals that follow it.
        self.risk_manager.sync_position(symbol, self.portfolio.get_position(symbol))
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

    def _open_short(
        self,
        symbol: str,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
        price: float,
    ) -> None:
        """Open or add to a short position.

        A short is sized exactly like a long: the signal strength times the
        configured position limit, less the gross exposure the symbol already
        carries. The sale credits its proceeds to the cash balance, so there
        is no cash constraint on the size of a short; the position size, the
        risk budget and the leverage limit of the risk manager are what bound
        it.

        The symbol must not be held long here: a short never flips a
        position, so the caller rejects a short signal against an open long
        instead of opening one.

        Args:
            symbol: Symbol that is traded.
            signal: The trading signal that triggered the trade.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to the trade.
            price: Execution price of the trade.

        Returns:
            None.

        """
        max_position_value = self.portfolio.total_value * self.risk_manager.position_limit.max_size
        target_value = max_position_value * signal.strength
        # The exposure of an open short is its gross value, so a short is
        # sized against the same budget as a long of the same size.
        current_value = abs(self.portfolio.get_position_value(symbol))
        available_value = target_value - current_value

        if available_value <= 0:
            return

        quantity = available_value / price
        self.portfolio.add_holding(
            symbol,
            -quantity,
            price,
            commission=self.config.commission,
            slippage=self.config.slippage,
        )
        # Keep the risk manager's view of the portfolio current, so a later
        # signal in this same bar is measured against the exposure this
        # trade just added instead of the exposure of the previous bar.
        self.risk_manager.sync_position(symbol, self.portfolio.get_position(symbol))
        # A short keeps the raw execution price as its cost basis, so the
        # entry fee that is deducted from the proceeds is booked as realized
        # PnL here. The cover books the price move and its own fee.
        entry_fee = quantity * price * (self.config.commission + self.config.slippage)
        trades_list.append(
            Trade(
                symbol=symbol,
                action="short",
                quantity=quantity,
                price=price,
                timestamp=timestamp,
                commission=self.config.commission,
                slippage=self.config.slippage,
                realized_pnl=-entry_fee,
            )
        )

    def _cover_short(
        self,
        symbol: str,
        signal: Signal,
        trades_list: list[Trade],
        timestamp: datetime,
        price: float,
        holding: Holding,
    ) -> None:
        """Buy back part of an open short position or close it completely.

        The short is covered in proportion to the signal strength and capped
        at the size of the position. Covering costs cash, so the cover is
        trimmed to what the cash balance can pay for.

        Args:
            symbol: Symbol that is traded.
            signal: The trading signal that triggered the trade.
            trades_list: List that executed trades are appended to.
            timestamp: Timestamp assigned to the trade.
            price: Execution price of the trade.
            holding: The open short position that is covered.

        Returns:
            None.

        """
        size = abs(holding.quantity)
        quantity = min(size * signal.strength, size)
        if quantity <= 0:
            return

        cost = quantity * price * (1 + self.config.commission + self.config.slippage)
        if cost > self.portfolio.cash:
            quantity = self.portfolio.cash / (
                price * (1 + self.config.commission + self.config.slippage)
            )
            if quantity <= 0:
                return

        avg_cost = holding.avg_cost
        self.portfolio.remove_holding(
            symbol,
            quantity,
            price,
            commission=self.config.commission,
            slippage=self.config.slippage,
        )
        # The short was opened at ``avg_cost``, so covering it realizes the
        # price move and pays the cover fee. The entry fee was already
        # booked by the short itself.
        realized_pnl = quantity * avg_cost - quantity * price * (
            1 + self.config.commission + self.config.slippage
        )
        # The risk manager's view of the portfolio is refreshed here as
        # well, so a short closed in this bar stops counting towards the
        # exposure of the signals that follow it.
        self.risk_manager.sync_position(symbol, self.portfolio.get_position(symbol))
        trades_list.append(
            Trade(
                symbol=symbol,
                action="cover",
                quantity=quantity,
                price=price,
                timestamp=timestamp,
                commission=self.config.commission,
                slippage=self.config.slippage,
                realized_pnl=realized_pnl,
            )
        )


def _resolve_backtest_config(
    config: Config | DataConfig | None,
    initial_capital: float | None,
    commission: float | None,
    slippage: float | None,
    periods_per_year: int | None,
) -> BacktestConfig:
    """Resolve the backtest settings a run is driven by.

    A value that is passed explicitly wins over the one the configuration
    carries, and the configuration wins over the built-in default. The
    ``backtest`` section of a full :class:`~quant_trading.config.settings.Config`
    is the only source of a configured value: a
    :class:`~quant_trading.config.settings.DataConfig` only describes the data
    layer, so the defaults of the backtest settings are used for it.

    The configuration is never modified: the resolved settings are a copy.

    Args:
        config: The configuration of the run, or ``None``.
        initial_capital: Explicit starting capital, or ``None``.
        commission: Explicit commission rate, or ``None``.
        slippage: Explicit slippage rate, or ``None``.
        periods_per_year: Explicit number of periods per year, or ``None``.

    Returns:
        The backtest settings the run is driven by.

    """
    base = config.backtest if isinstance(config, Config) else BacktestConfig()
    overrides: dict[str, Any] = {}
    if initial_capital is not None:
        overrides["initial_capital"] = initial_capital
    if commission is not None:
        overrides["commission"] = commission
    if slippage is not None:
        overrides["slippage"] = slippage
    if periods_per_year is not None:
        overrides["periods_per_year"] = periods_per_year
    return replace(base, **overrides)


def _resolve_data_interval(
    config: Config | DataConfig | None,
    interval: str | None,
) -> str:
    """Resolve the bar interval a run fetches with.

    A value that is passed explicitly wins over the one the configuration
    carries, and the configuration wins over the built-in default. The
    ``default_interval`` of the ``data`` section is the configured value: a
    :class:`~quant_trading.config.settings.DataConfig` describes the data
    layer, so it is the section that carries the interval, and a full
    :class:`~quant_trading.config.settings.Config` carries it as well.

    The configuration is never modified.

    Args:
        config: The configuration of the run, or ``None``.
        interval: Explicit interval, or ``None``.

    Returns:
        The interval the run is driven by (``"1d"`` when nothing is
        configured).

    """
    if interval is not None:
        return interval
    if isinstance(config, Config):
        return config.data.default_interval
    if isinstance(config, DataConfig):
        return config.default_interval
    return "1d"


def run_backtest(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_capital: float | None = None,
    commission: float | None = None,
    slippage: float | None = None,
    interval: str | None = None,
    data_manager: DataManager | None = None,
    config: Config | DataConfig | None = None,
    periods_per_year: int | None = None,
) -> BacktestResult:
    """Run a single strategy backtest.

    When a full :class:`~quant_trading.config.settings.Config` is given, its
    ``backtest``, ``risk`` and ``portfolio`` sections drive the run: the
    ``backtest`` section provides the starting capital, the costs, the
    annualization period and the engine switches, the ``risk`` section
    provides the limits of the risk manager and the ``portfolio`` section
    provides the limit on the number of open positions. A value that is
    passed explicitly wins over the configured one, and the configured one
    wins over the built-in default. The configuration itself is never
    modified.

    Args:
        strategy: The strategy to backtest.
        symbols: List of symbols to trade.
        start: Start date for backtest.
        end: End date for backtest.
        initial_capital: Initial capital. Defaults to the configured value, or
            to 100000.0 when nothing is configured.
        commission: Commission rate. Defaults to the configured value, or to
            0.001 when nothing is configured.
        slippage: Slippage rate. Defaults to the configured value, or to 0.0005
            when nothing is configured.
        interval: Data interval (default: "1d").
        data_manager: Optional DataManager for offline/testing. If not provided
            and no config is given, a shared default DataManager with
            YFinanceProvider will be used (requires network).
        config: Optional Config or DataConfig. When no data manager is given,
            a DataManager is created from the config (supporting
            offline/synthetic modes). A full Config also configures the
            backtest, the risk limits and the position limit.
        periods_per_year: Trading periods per year used to annualize the
            return, volatility, Sharpe, Sortino and Calmar metrics. Defaults to
            the configured value, or to 252 (daily data) when nothing is
            configured.

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

        A configuration drives the risk limits of the run::

            from quant_trading.config.settings import Config, RiskConfig

            config = Config(risk=RiskConfig(max_position_size=0.05))
            result = run_backtest(
                strategy=strategy,
                symbols=symbols,
                start=start,
                end=end,
                config=config,
                data_manager=data_manager,
            )
            assert result is not None

    """
    backtest_config = _resolve_backtest_config(
        config,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        periods_per_year=periods_per_year,
    )

    if data_manager is None:
        if config is not None:
            data_config = config.data if isinstance(config, Config) else config
            data_manager = create_data_manager_from_config(data_config)
        else:
            data_manager = get_default_data_manager()

    # The interval is resolved the same way as the backtest settings: an
    # explicit value wins over the configured one, and the configured one
    # wins over the built-in default. The data section carries it.
    interval = _resolve_data_interval(config, interval)

    if isinstance(config, Config):
        # The full configuration drives the risk limits and the position limit
        # of the run. A copy is used so the caller's configuration is untouched.
        engine_config: BacktestConfig | Config = replace(config, backtest=backtest_config)
    else:
        engine_config = backtest_config

    engine = BacktestEngine(config=engine_config, data_manager=data_manager)
    engine.add_strategy(strategy)
    return engine.run(symbols, start, end, interval)
