from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from qtrading.config import get_settings
from qtrading.strategy import Order, OrderSide, Position


@dataclass
class RiskLimits:
    max_drawdown: Decimal
    max_position_size: Decimal
    max_daily_loss: Decimal
    var_confidence: float
    correlation_threshold: float


@dataclass
class RiskMetrics:
    current_drawdown: Decimal
    daily_pnl: Decimal
    portfolio_var: Decimal
    max_correlation: float
    position_count: int
    total_exposure: Decimal
    leverage: float


class RiskManager:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.limits = RiskLimits(
            max_drawdown=Decimal(str(settings.risk.max_drawdown)),
            max_position_size=Decimal(str(settings.risk.max_position_size)),
            max_daily_loss=Decimal(str(settings.risk.max_daily_loss)),
            var_confidence=settings.risk.var_confidence,
            correlation_threshold=settings.risk.correlation_threshold,
        )
        self.daily_start_value: Decimal | None = None
        self.daily_start_date: datetime | None = None
        self.peak_value: Decimal = Decimal("0")
        self.position_history: list[Position] = []

    def reset_daily(self, portfolio_value: Decimal, current_time: datetime) -> None:
        if self.daily_start_date is None or self.daily_start_date.date() != current_time.date():
            self.daily_start_value = portfolio_value
            self.daily_start_date = current_time
            logger.info(f"Daily reset: start value = {portfolio_value}")

    def update_peak(self, portfolio_value: Decimal) -> None:
        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value

    def get_current_drawdown(self, portfolio_value: Decimal) -> Decimal:
        if self.peak_value == 0:
            return Decimal("0")
        return (self.peak_value - portfolio_value) / self.peak_value

    def get_daily_pnl(self, portfolio_value: Decimal) -> Decimal:
        if self.daily_start_value is None:
            return Decimal("0")
        return portfolio_value - self.daily_start_value

    def check_position_size(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        portfolio_value: Decimal,
    ) -> tuple[bool, str | None]:
        position_value = abs(quantity) * price
        max_allowed = portfolio_value * self.limits.max_position_size

        if position_value > max_allowed:
            return False, f"Position size {position_value} exceeds max {max_allowed}"
        return True, None

    def check_drawdown(self, portfolio_value: Decimal) -> tuple[bool, str | None]:
        drawdown = self.get_current_drawdown(portfolio_value)
        if drawdown > self.limits.max_drawdown:
            return False, f"Max drawdown exceeded: {drawdown:.2%} > {self.limits.max_drawdown:.2%}"
        return True, None

    def check_daily_loss(self, portfolio_value: Decimal) -> tuple[bool, str | None]:
        daily_pnl = self.get_daily_pnl(portfolio_value)
        max_loss = self.daily_start_value * self.limits.max_daily_loss if self.daily_start_value else Decimal("0")

        if daily_pnl < -max_loss:
            return False, f"Daily loss limit exceeded: {daily_pnl} < -{max_loss}"
        return True, None

    def check_correlation(
        self,
        new_symbol: str,
        new_quantity: Decimal,
        new_price: Decimal,
        current_positions: dict[str, Position],
        price_history: dict[str, pd.Series],
    ) -> tuple[bool, str | None]:
        if not current_positions or new_symbol not in price_history:
            return True, None

        new_returns = price_history[new_symbol].pct_change().dropna()
        if len(new_returns) < 30:
            return True, None

        for symbol, _position in current_positions.items():
            if symbol == new_symbol or symbol not in price_history:
                continue

            existing_returns = price_history[symbol].pct_change().dropna()
            common_idx = new_returns.index.intersection(existing_returns.index)
            if len(common_idx) < 30:
                continue

            corr = new_returns.loc[common_idx].corr(existing_returns.loc[common_idx])
            if abs(corr) > self.limits.correlation_threshold:
                return False, f"High correlation with {symbol}: {corr:.2f} > {self.limits.correlation_threshold}"

        return True, None

    def calculate_var(
        self,
        positions: dict[str, Position],
        price_history: dict[str, pd.Series],
        portfolio_value: Decimal,
    ) -> Decimal:
        if not positions or not price_history:
            return Decimal("0")

        returns_list = []
        weights = []

        for symbol, position in positions.items():
            if symbol in price_history:
                returns = price_history[symbol].pct_change().dropna()
                if len(returns) > 0:
                    returns_list.append(returns.values)
                    position_value = abs(position.quantity) * position.current_price
                    weights.append(float(position_value / portfolio_value))

        if not returns_list:
            return Decimal("0")

        min_len = min(len(r) for r in returns_list)
        returns_matrix = np.column_stack([r[-min_len:] for r in returns_list])
        weights = np.array(weights)
        weights = weights / weights.sum() if weights.sum() > 0 else weights

        portfolio_returns = returns_matrix @ weights
        var = np.percentile(portfolio_returns, (1 - self.limits.var_confidence) * 100)

        return Decimal(str(abs(var) * float(portfolio_value)))

    def check_order(
        self,
        order: Order,
        portfolio_value: Decimal,
        current_positions: dict[str, Position],
        price_history: dict[str, pd.Series],
        current_time: datetime,
    ) -> tuple[bool, list[str]]:
        errors = []

        self.reset_daily(portfolio_value, current_time)
        self.update_peak(portfolio_value)

        if order.side in (OrderSide.BUY, OrderSide.SELL):
            price = order.price or Decimal("0")
            if price > 0:
                ok, err = self.check_position_size(order.symbol, order.quantity, price, portfolio_value)
                if not ok:
                    errors.append(err)

                ok, err = self.check_correlation(order.symbol, order.quantity, price, current_positions, price_history)
                if not ok:
                    errors.append(err)

        ok, err = self.check_drawdown(portfolio_value)
        if not ok:
            errors.append(err)

        ok, err = self.check_daily_loss(portfolio_value)
        if not ok:
            errors.append(err)

        return len(errors) == 0, errors

    def get_metrics(
        self,
        portfolio_value: Decimal,
        positions: dict[str, Position],
        price_history: dict[str, pd.Series],
    ) -> RiskMetrics:
        self.update_peak(portfolio_value)

        return RiskMetrics(
            current_drawdown=self.get_current_drawdown(portfolio_value),
            daily_pnl=self.get_daily_pnl(portfolio_value),
            portfolio_var=self.calculate_var(positions, price_history, portfolio_value),
            max_correlation=0.0,
            position_count=len(positions),
            total_exposure=sum(abs(p.quantity) * p.current_price for p in positions.values()),
            leverage=float(sum(abs(p.quantity) * p.current_price for p in positions.values()) / portfolio_value)
            if portfolio_value > 0 else 0.0,
        )

    def should_reduce_positions(self, portfolio_value: Decimal) -> bool:
        drawdown = self.get_current_drawdown(portfolio_value)
        return drawdown > self.limits.max_drawdown * Decimal("0.8")

    def get_reduction_factor(self, portfolio_value: Decimal) -> Decimal:
        drawdown = self.get_current_drawdown(portfolio_value)
        if drawdown <= self.limits.max_drawdown * Decimal("0.5"):
            return Decimal("1.0")
        elif drawdown >= self.limits.max_drawdown:
            return Decimal("0.0")
        else:
            progress = (drawdown - self.limits.max_drawdown * Decimal("0.5")) / (self.limits.max_drawdown * Decimal("0.5"))
            return Decimal("1.0") - progress * Decimal("0.5")
