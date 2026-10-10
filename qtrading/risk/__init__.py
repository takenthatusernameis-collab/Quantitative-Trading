from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

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
    max_sector_exposure: Decimal = Decimal("0.3")
    max_factor_exposure: Decimal = Decimal("0.25")
    max_portfolio_leverage: Decimal = Decimal("1.0")


@dataclass
class RiskMetrics:
    current_drawdown: Decimal
    daily_pnl: Decimal
    portfolio_var: Decimal
    max_correlation: float
    position_count: int
    total_exposure: Decimal
    leverage: float
    sector_exposure: dict[str, float] = field(default_factory=dict)
    factor_exposure: dict[str, float] = field(default_factory=dict)
    portfolio_beta: float = 0.0


@dataclass
class StressTestResult:
    scenario_name: str
    initial_capital: float
    final_capital: float
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    recovery_time: int | None = None


@dataclass
class PositionSizeResult:
    symbol: str
    recommended_size: Decimal
    max_size: Decimal
    kelly_size: Decimal
    volatility_target_size: Decimal
    reason: str


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
        max_loss = (
            self.daily_start_value * self.limits.max_daily_loss
            if self.daily_start_value
            else Decimal("0")
        )

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
                msg = (
                    f"High correlation with {symbol}: {corr:.2f} > "
                    f"{self.limits.correlation_threshold}"
                )
                return (False, msg)

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
                ok, err = self.check_position_size(
                    order.symbol, order.quantity, price, portfolio_value
                )
                if not ok:
                    errors.append(err)

                ok, err = self.check_correlation(
                    order.symbol, order.quantity, price, current_positions, price_history
                )
                if not ok:
                    errors.append(err)

        ok, err = self.check_drawdown(portfolio_value)
        if not ok:
            errors.append(err)

        ok, err = self.check_daily_loss(portfolio_value)
        if not ok:
            errors.append(err)

        return len(errors) == 0, errors

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
            progress = (drawdown - self.limits.max_drawdown * Decimal("0.5")) / (
                self.limits.max_drawdown * Decimal("0.5")
            )
            return Decimal("1.0") - progress * Decimal("0.5")

    def calculate_kelly_size(
        self,
        symbol: str,
        win_rate: float,
        avg_win: Decimal,
        avg_loss: Decimal,
        portfolio_value: Decimal,
        price: Decimal,
    ) -> Decimal:
        if avg_loss == 0 or avg_win == 0:
            return Decimal("0")
        win_loss_ratio = float(avg_win / abs(avg_loss))
        kelly_pct = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        kelly_pct = max(0.0, min(kelly_pct, 0.25))
        kelly_value = portfolio_value * Decimal(str(kelly_pct))
        return kelly_value / price if price > 0 else Decimal("0")

    def calculate_volatility_target_size(
        self,
        symbol: str,
        price: Decimal,
        volatility: Decimal,
        portfolio_value: Decimal,
        target_vol: Decimal = Decimal("0.01"),
    ) -> Decimal:
        if volatility <= 0 or price <= 0:
            return Decimal("0")
        position_value = portfolio_value * target_vol / volatility
        return position_value / price

    def calculate_dynamic_position_size(
        self,
        symbol: str,
        price: Decimal,
        volatility: Decimal,
        portfolio_value: Decimal,
        win_rate: float = 0.5,
        avg_win: Decimal = Decimal("0"),
        avg_loss: Decimal = Decimal("0"),
        method: str = "volatility",
    ) -> PositionSizeResult:
        if price <= 0:
            return PositionSizeResult(
                symbol=symbol,
                recommended_size=Decimal("0"),
                max_size=Decimal("0"),
                kelly_size=Decimal("0"),
                volatility_target_size=Decimal("0"),
                reason="Invalid price",
            )
        max_size = (
            portfolio_value * self.limits.max_position_size / price
        )
        kelly_size = self.calculate_kelly_size(
            symbol, win_rate, avg_win, avg_loss, portfolio_value, price
        )
        vol_size = self.calculate_volatility_target_size(
            symbol, price, volatility, portfolio_value
        )

        if method == "kelly":
            recommended = min(kelly_size, max_size)
            reason = "Kelly criterion sizing"
        elif method == "volatility":
            recommended = min(vol_size, max_size)
            reason = "Volatility targeting"
        else:
            recommended = min(kelly_size, vol_size, max_size)
            reason = "Combined Kelly + volatility"

        return PositionSizeResult(
            symbol=symbol,
            recommended_size=recommended,
            max_size=max_size,
            kelly_size=kelly_size,
            volatility_target_size=vol_size,
            reason=reason,
        )

    def check_sector_exposure(
        self,
        positions: dict[str, Position],
        sector_map: dict[str, str],
        portfolio_value: Decimal,
    ) -> tuple[bool, list[str]]:
        sector_exposure: dict[str, Decimal] = {}
        for symbol, pos in positions.items():
            sector = sector_map.get(symbol, "unknown")
            pos_value = abs(pos.quantity) * pos.current_price
            sector_exposure[sector] = sector_exposure.get(sector, Decimal("0")) + pos_value

        errors = []
        for sector, exposure in sector_exposure.items():
            pct = exposure / portfolio_value if portfolio_value > 0 else Decimal("0")
            if pct > self.limits.max_sector_exposure:
                msg = (
                    f"Sector {sector} exposure {pct:.2%} exceeds max "
                    f"{self.limits.max_sector_exposure:.2%}"
                )
                errors.append(msg)
        return len(errors) == 0, errors

    def check_portfolio_leverage(
        self,
        positions: dict[str, Position],
        portfolio_value: Decimal,
    ) -> tuple[bool, str | None]:
        total_exposure = sum(abs(p.quantity) * p.current_price for p in positions.values())
        leverage = total_exposure / portfolio_value if portfolio_value > 0 else Decimal("0")
        if leverage > self.limits.max_portfolio_leverage:
            msg = (
                f"Portfolio leverage {leverage:.2f} exceeds max "
                f"{self.limits.max_portfolio_leverage:.2f}"
            )
            return False, msg
        return True, None

    def run_stress_test(
        self,
        initial_capital: float,
        scenario_returns: list[float],
    ) -> StressTestResult:
        equity = [initial_capital]
        for r in scenario_returns:
            equity.append(equity[-1] * (1 + r))

        equity_arr = np.array(equity)
        final_capital = float(equity_arr[-1])
        total_return = (final_capital / initial_capital) - 1

        peak = np.maximum.accumulate(equity_arr)
        drawdown = (peak - equity_arr) / peak
        max_dd = float(np.max(drawdown))

        returns_arr = np.diff(equity_arr) / equity_arr[:-1]
        if np.std(returns_arr) > 0:
            sharpe = float(np.mean(returns_arr) / np.std(returns_arr) * np.sqrt(252))
        else:
            sharpe = 0.0

        recovery_time = None
        peak_idx = np.argmax(peak)
        if peak_idx < len(equity_arr) - 1:
            peak_val = peak[peak_idx]
            for i in range(peak_idx + 1, len(equity_arr)):
                if equity_arr[i] >= peak_val:
                    recovery_time = i - peak_idx
                    break

        return StressTestResult(
            scenario_name="custom",
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=float(total_return),
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            recovery_time=recovery_time,
        )

    def get_metrics(
        self,
        portfolio_value: Decimal,
        positions: dict[str, Position],
        price_history: dict[str, pd.Series],
    ) -> RiskMetrics:
        self.update_peak(portfolio_value)

        sector_exposure: dict[str, float] = {}
        factor_exposure: dict[str, float] = {}

        total_exposure = sum(abs(p.quantity) * p.current_price for p in positions.values())
        leverage = float(total_exposure / portfolio_value) if portfolio_value > 0 else 0.0

        return RiskMetrics(
            current_drawdown=self.get_current_drawdown(portfolio_value),
            daily_pnl=self.get_daily_pnl(portfolio_value),
            portfolio_var=self.calculate_var(positions, price_history, portfolio_value),
            max_correlation=0.0,
            position_count=len(positions),
            total_exposure=total_exposure,
            leverage=leverage,
            sector_exposure=sector_exposure,
            factor_exposure=factor_exposure,
        )
