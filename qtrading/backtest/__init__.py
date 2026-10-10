from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from loguru import logger

from qtrading.backtest.walkforward import (
    WalkForwardAnalyzer,
    WalkForwardResult,
    WalkForwardSummary,
    WalkForwardWindow,
)
from qtrading.config import get_settings
from qtrading.strategy import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SignalType,
    Strategy,
    StrategyContext,
)


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    exit_time: datetime | None
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    side: str
    pnl: Decimal | None = None
    commission: Decimal = Decimal("0")
    strategy_id: str | None = None


@dataclass
class BacktestResult:
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Decimal
    total_return_pct: float
    annualized_return: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)


class Portfolio:
    def __init__(self, initial_capital: Decimal, commission_rate: Decimal, slippage_rate: Decimal):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self.current_time: datetime | None = None

    def get_portfolio_value(self, prices: dict[str, Decimal]) -> Decimal:
        value = self.cash
        for symbol, position in self.positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                if position.side == "long":
                    value += position.quantity * current_price
                else:
                    value += position.quantity * (2 * position.entry_price - current_price)
        return value

    def get_available_capital(self) -> Decimal:
        used_margin = sum(
            pos.quantity * pos.entry_price for pos in self.positions.values() if pos.quantity > 0
        )
        return self.cash - used_margin

    def update_positions(self, prices: dict[str, Decimal], current_time: datetime) -> None:
        self.current_time = current_time
        for symbol, position in self.positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                if position.side == "long":
                    unrealized = (current_price - position.entry_price) * position.quantity
                else:
                    unrealized = (position.entry_price - current_price) * abs(position.quantity)

                self.positions[symbol] = Position(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized,
                    realized_pnl=position.realized_pnl,
                    side=position.side,
                    timestamp=current_time,
                    strategy_id=position.strategy_id,
                )

    def execute_order(self, order: Order, fill_price: Decimal, current_time: datetime) -> Trade | None:
        commission = fill_price * order.quantity * self.commission_rate
        slippage = fill_price * order.quantity * self.slippage_rate
        total_cost = fill_price * order.quantity + commission + slippage

        if order.side == OrderSide.BUY:
            if self.cash < total_cost:
                logger.warning(f"Insufficient cash for order {order.id}")
                return None
            self.cash -= total_cost

            if order.symbol in self.positions:
                pos = self.positions[order.symbol]
                if pos.side == "long":
                    new_quantity = pos.quantity + order.quantity
                    new_entry = (pos.entry_price * pos.quantity + fill_price * order.quantity) / new_quantity
                    self.positions[order.symbol] = Position(
                        symbol=pos.symbol,
                        quantity=new_quantity,
                        entry_price=new_entry,
                        current_price=fill_price,
                        unrealized_pnl=Decimal("0"),
                        realized_pnl=pos.realized_pnl,
                        side="long",
                        timestamp=current_time,
                        strategy_id=order.strategy_id,
                    )
                else:
                    new_quantity = pos.quantity + order.quantity
                    if new_quantity == 0:
                        realized = (pos.entry_price - fill_price) * abs(pos.quantity) - pos.realized_pnl
                        trade = Trade(
                            symbol=order.symbol,
                            entry_time=pos.timestamp,
                            exit_time=current_time,
                            entry_price=pos.entry_price,
                            exit_price=fill_price,
                            quantity=abs(pos.quantity),
                            side="short",
                            pnl=realized - commission - slippage,
                            commission=commission + slippage,
                            strategy_id=pos.strategy_id,
                        )
                        self.trades.append(trade)
                        self.cash += realized
                        del self.positions[order.symbol]
                    elif new_quantity < 0:
                        self.positions[order.symbol] = Position(
                            symbol=pos.symbol,
                            quantity=new_quantity,
                            entry_price=pos.entry_price,
                            current_price=fill_price,
                            unrealized_pnl=Decimal("0"),
                            realized_pnl=pos.realized_pnl,
                            side="short",
                            timestamp=current_time,
                            strategy_id=order.strategy_id,
                        )
                    else:
                        realized = (pos.entry_price - fill_price) * abs(pos.quantity)
                        remaining = new_quantity
                        trade = Trade(
                            symbol=order.symbol,
                            entry_time=pos.timestamp,
                            exit_time=current_time,
                            entry_price=pos.entry_price,
                            exit_price=fill_price,
                            quantity=abs(pos.quantity),
                            side="short",
                            pnl=realized - commission - slippage,
                            commission=commission + slippage,
                            strategy_id=pos.strategy_id,
                        )
                        self.trades.append(trade)
                        self.cash += realized
                        self.positions[order.symbol] = Position(
                            symbol=order.symbol,
                            quantity=remaining,
                            entry_price=fill_price,
                            current_price=fill_price,
                            unrealized_pnl=Decimal("0"),
                            realized_pnl=Decimal("0"),
                            side="long",
                            timestamp=current_time,
                            strategy_id=order.strategy_id,
                        )
            else:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    side="long",
                    timestamp=current_time,
                    strategy_id=order.strategy_id,
                )

        elif order.side == OrderSide.SELL:
            if order.symbol in self.positions:
                pos = self.positions[order.symbol]
                if pos.side == "short":
                    new_quantity = pos.quantity - order.quantity
                    new_entry = (pos.entry_price * abs(pos.quantity) + fill_price * order.quantity) / abs(new_quantity)
                    self.positions[order.symbol] = Position(
                        symbol=pos.symbol,
                        quantity=new_quantity,
                        entry_price=new_entry,
                        current_price=fill_price,
                        unrealized_pnl=Decimal("0"),
                        realized_pnl=pos.realized_pnl,
                        side="short",
                        timestamp=current_time,
                        strategy_id=order.strategy_id,
                    )
                else:
                    new_quantity = pos.quantity - order.quantity
                    if new_quantity == 0:
                        realized = (fill_price - pos.entry_price) * pos.quantity
                        trade = Trade(
                            symbol=order.symbol,
                            entry_time=pos.timestamp,
                            exit_time=current_time,
                            entry_price=pos.entry_price,
                            exit_price=fill_price,
                            quantity=pos.quantity,
                            side="long",
                            pnl=realized - commission - slippage,
                            commission=commission + slippage,
                            strategy_id=pos.strategy_id,
                        )
                        self.trades.append(trade)
                        self.cash += fill_price * order.quantity - commission - slippage
                        del self.positions[order.symbol]
                    elif new_quantity > 0:
                        realized = (fill_price - pos.entry_price) * order.quantity
                        trade = Trade(
                            symbol=order.symbol,
                            entry_time=pos.timestamp,
                            exit_time=current_time,
                            entry_price=pos.entry_price,
                            exit_price=fill_price,
                            quantity=order.quantity,
                            side="long",
                            pnl=realized - commission - slippage,
                            commission=commission + slippage,
                            strategy_id=pos.strategy_id,
                        )
                        self.trades.append(trade)
                        self.cash += fill_price * order.quantity - commission - slippage
                        self.positions[order.symbol] = Position(
                            symbol=pos.symbol,
                            quantity=new_quantity,
                            entry_price=pos.entry_price,
                            current_price=fill_price,
                            unrealized_pnl=Decimal("0"),
                            realized_pnl=pos.realized_pnl,
                            side="long",
                            timestamp=current_time,
                            strategy_id=order.strategy_id,
                        )
                    else:
                        realized = (fill_price - pos.entry_price) * pos.quantity
                        remaining = abs(new_quantity)
                        trade = Trade(
                            symbol=order.symbol,
                            entry_time=pos.timestamp,
                            exit_time=current_time,
                            entry_price=pos.entry_price,
                            exit_price=fill_price,
                            quantity=pos.quantity,
                            side="long",
                            pnl=realized - commission - slippage,
                            commission=commission + slippage,
                            strategy_id=pos.strategy_id,
                        )
                        self.trades.append(trade)
                        self.cash += fill_price * pos.quantity - commission - slippage
                        self.positions[order.symbol] = Position(
                            symbol=order.symbol,
                            quantity=-remaining,
                            entry_price=fill_price,
                            current_price=fill_price,
                            unrealized_pnl=Decimal("0"),
                            realized_pnl=Decimal("0"),
                            side="short",
                            timestamp=current_time,
                            strategy_id=order.strategy_id,
                        )
            else:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=-order.quantity,
                    entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    side="short",
                    timestamp=current_time,
                    strategy_id=order.strategy_id,
                )

        return None

    def record_equity(self, prices: dict[str, Decimal], current_time: datetime) -> None:
        value = self.get_portfolio_value(prices)
        self.equity_curve.append((current_time, value))


class BacktestEngine:
    def __init__(
        self,
        initial_capital: Decimal | None = None,
        commission_rate: Decimal | None = None,
        slippage_rate: Decimal | None = None,
        max_positions: int | None = None,
    ):
        settings = get_settings()
        self.initial_capital = initial_capital or Decimal(str(settings.backtest.initial_capital))
        self.commission_rate = commission_rate or Decimal(str(settings.backtest.commission_rate))
        self.slippage_rate = slippage_rate or Decimal(str(settings.backtest.slippage_rate))
        self.max_positions = max_positions or settings.backtest.max_positions
        self.portfolio = Portfolio(self.initial_capital, self.commission_rate, self.slippage_rate)

    def run(
        self,
        strategy: Strategy,
        market_data: dict[str, pd.DataFrame],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> BacktestResult:
        import asyncio
        all_timestamps = set()
        for df in market_data.values():
            if not df.empty:
                all_timestamps.update(df.index)

        timestamps = sorted(all_timestamps)
        if start_date:
            timestamps = [t for t in timestamps if t >= start_date]
        if end_date:
            timestamps = [t for t in timestamps if t <= end_date]

        for ts in timestamps:
            current_prices = {}
            current_data = {}

            for symbol, df in market_data.items():
                if ts in df.index:
                    row = df.loc[ts]
                    current_prices[symbol] = Decimal(str(row["close"]))
                    current_data[symbol] = df[df.index <= ts]

            self.portfolio.update_positions(current_prices, ts)
            self.portfolio.record_equity(current_prices, ts)

            context = StrategyContext(
                current_time=ts,
                portfolio_value=self.portfolio.get_portfolio_value(current_prices),
                positions=self.portfolio.positions.copy(),
                available_capital=self.portfolio.get_available_capital(),
                market_data=current_data,
            )

            signals = asyncio.run(strategy.run(context))

            for signal in signals:
                if signal.symbol not in current_prices:
                    continue

                price = current_prices[signal.symbol]
                position = self.portfolio.positions.get(signal.symbol)
                has_position = position is not None and position.quantity != 0

                order = None
                if signal.signal_type == SignalType.BUY and not has_position:
                    available = self.portfolio.get_available_capital()
                    position_value = available * Decimal(str(strategy.params.parameters.get("position_size", 0.1)))
                    quantity = position_value / price
                    order = Order(
                        id=f"{strategy.params.name}_{signal.symbol}_{ts.timestamp()}",
                        symbol=signal.symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        strategy_id=strategy.params.name,
                    )
                elif signal.signal_type == SignalType.SELL and not has_position:
                    available = self.portfolio.get_available_capital()
                    position_value = available * Decimal(str(strategy.params.parameters.get("position_size", 0.1)))
                    quantity = position_value / price
                    order = Order(
                        id=f"{strategy.params.name}_{signal.symbol}_{ts.timestamp()}",
                        symbol=signal.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        strategy_id=strategy.params.name,
                    )
                elif signal.signal_type == SignalType.CLOSE_LONG and has_position and position.quantity > 0:
                    order = Order(
                        id=f"{strategy.params.name}_{signal.symbol}_{ts.timestamp()}",
                        symbol=signal.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=position.quantity,
                        strategy_id=strategy.params.name,
                    )
                elif signal.signal_type == SignalType.CLOSE_SHORT and has_position and position.quantity < 0:
                    order = Order(
                        id=f"{strategy.params.name}_{signal.symbol}_{ts.timestamp()}",
                        symbol=signal.symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=abs(position.quantity),
                        strategy_id=strategy.params.name,
                    )

                if order:
                    fill_price = price * (Decimal("1") + self.slippage_rate)
                    if order.side == OrderSide.SELL:
                        fill_price = price * (Decimal("1") - self.slippage_rate)
                    self.portfolio.execute_order(order, fill_price, ts)

        for symbol, position in self.portfolio.positions.items():
            if symbol in current_prices:
                price = current_prices[symbol]
                if position.side == "long":
                    realized = (price - position.entry_price) * position.quantity
                else:
                    realized = (position.entry_price - price) * abs(position.quantity)

                trade = Trade(
                    symbol=symbol,
                    entry_time=position.timestamp,
                    exit_time=timestamps[-1],
                    entry_price=position.entry_price,
                    exit_price=price,
                    quantity=abs(position.quantity),
                    side=position.side,
                    pnl=realized,
                    commission=Decimal("0"),
                    strategy_id=position.strategy_id,
                )
                self.portfolio.trades.append(trade)

        return self._calculate_results()

    def _calculate_results(self) -> BacktestResult:
        final_capital = self.portfolio.equity_curve[-1][1] if self.portfolio.equity_curve else self.initial_capital
        total_return = final_capital - self.initial_capital
        total_return_pct = float(total_return / self.initial_capital * 100)

        equity_values = [float(v) for _, v in self.portfolio.equity_curve]
        if len(equity_values) > 1:
            returns = np.diff(equity_values) / equity_values[:-1]
            daily_returns = returns

            if len(daily_returns) > 0 and np.std(daily_returns) > 0:
                sharpe_ratio = float(np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252))
                downside_returns = daily_returns[daily_returns < 0]
                if len(downside_returns) > 0 and np.std(downside_returns) > 0:
                    sortino_ratio = float(np.mean(daily_returns) / np.std(downside_returns) * np.sqrt(252))
                else:
                    sortino_ratio = 0.0
            else:
                sharpe_ratio = 0.0
                sortino_ratio = 0.0

            peak = np.maximum.accumulate(equity_values)
            drawdown = (peak - equity_values) / peak
            max_drawdown_pct = float(np.max(drawdown) * 100)
            max_drawdown = Decimal(str(np.max(drawdown) * float(self.initial_capital)))
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0
            max_drawdown_pct = 0.0
            max_drawdown = Decimal("0")
            daily_returns = []

        winning_trades = [t for t in self.portfolio.trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in self.portfolio.trades if t.pnl and t.pnl <= 0]

        win_rate = len(winning_trades) / len(self.portfolio.trades) * 100 if self.portfolio.trades else 0
        avg_win = Decimal(str(np.mean([float(t.pnl) for t in winning_trades]))) if winning_trades else Decimal("0")
        avg_loss = Decimal(str(np.mean([float(t.pnl) for t in losing_trades]))) if losing_trades else Decimal("0")

        gross_profit = sum(float(t.pnl) for t in winning_trades) if winning_trades else 0
        gross_loss = abs(sum(float(t.pnl) for t in losing_trades)) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        return BacktestResult(
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=0.0,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(self.portfolio.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            trades=self.portfolio.trades,
            equity_curve=self.portfolio.equity_curve,
            daily_returns=daily_returns.tolist() if len(daily_returns) > 0 else [],
        )


__all__ = [
    "Trade",
    "BacktestResult",
    "Portfolio",
    "BacktestEngine",
    "WalkForwardAnalyzer",
    "WalkForwardWindow",
    "WalkForwardResult",
    "WalkForwardSummary",
]
