from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np

from qtrading.backtest import BacktestResult


@dataclass
class MonteCarloResult:
    num_simulations: int
    num_bars: int
    initial_capital: float
    final_capitals: list[float]
    total_returns: list[float]
    max_drawdowns: list[float]
    sharpe_ratios: list[float]
    win_rates: list[float]
    profit_factors: list[float]
    mean_final_capital: float
    std_final_capital: float
    median_final_capital: float
    percentile_5_final_capital: float
    percentile_95_final_capital: float
    mean_total_return: float
    std_total_return: float
    mean_max_drawdown: float
    max_max_drawdown: float
    mean_sharpe: float
    min_sharpe: float
    max_sharpe: float
    mean_win_rate: float
    prob_profit: float
    mean_profit_factor: float
    best_run_capital: float
    worst_run_capital: float


class MonteCarloSimulator:
    """Simulates many possible price paths by resampling historical returns."""

    def __init__(
        self,
        initial_capital: Decimal | float = Decimal("100000"),
        commission_rate: Decimal | float = Decimal("0.001"),
        slippage_rate: Decimal | float = Decimal("0.0005"),
        random_seed: int | None = None,
    ):
        self.initial_capital = float(initial_capital)
        self.commission_rate = float(commission_rate)
        self.slippage_rate = float(slippage_rate)
        self._rng = np.random.default_rng(random_seed)

    def simulate(
        self,
        equity_curve: list[tuple],
        num_simulations: int = 1000,
        num_bars: int | None = None,
    ) -> MonteCarloResult:
        if not equity_curve:
            raise ValueError("equity_curve is empty")

        values = np.array([float(v) for _, v in equity_curve], dtype=np.float64)
        returns = np.diff(values) / values[:-1]

        if num_bars is None:
            num_bars = len(values) - 1

        final_capitals = np.zeros(num_simulations, dtype=np.float64)
        max_drawdowns = np.zeros(num_simulations, dtype=np.float64)
        sharpe_ratios = np.zeros(num_simulations, dtype=np.float64)
        win_rates = np.zeros(num_simulations, dtype=np.float64)
        profit_factors = np.zeros(num_simulations, dtype=np.float64)

        for i in range(num_simulations):
            sampled = self._rng.choice(returns, size=num_bars, replace=True)
            equity = np.zeros(num_bars + 1, dtype=np.float64)
            equity[0] = self.initial_capital
            equity[1:] = self.initial_capital * np.cumprod(1.0 + sampled)

            final_capitals[i] = equity[-1]

            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            max_drawdowns[i] = float(np.max(drawdown))

            if len(equity) > 1:
                sim_returns = np.diff(equity) / equity[:-1]
                std = np.std(sim_returns)
                if std > 0:
                    sharpe_ratios[i] = float(np.mean(sim_returns) / std * np.sqrt(252))
                else:
                    sharpe_ratios[i] = 0.0
            else:
                sharpe_ratios[i] = 0.0

            positive = sim_returns[sim_returns > 0]
            negative = sim_returns[sim_returns < 0]
            if len(positive) > 0 and len(negative) > 0:
                gross_profit = float(np.sum(positive))
                gross_loss = abs(float(np.sum(negative)))
                profit_factors[i] = gross_profit / gross_loss if gross_loss > 0 else 0.0
            else:
                profit_factors[i] = 0.0

            win_rates[i] = float(len(positive) / len(sim_returns) * 100) if len(sim_returns) > 0 else 0.0

        total_returns = (final_capitals - self.initial_capital) / self.initial_capital * 100

        return MonteCarloResult(
            num_simulations=num_simulations,
            num_bars=num_bars,
            initial_capital=self.initial_capital,
            final_capitals=final_capitals.tolist(),
            total_returns=total_returns.tolist(),
            max_drawdowns=max_drawdowns.tolist(),
            sharpe_ratios=sharpe_ratios.tolist(),
            win_rates=win_rates.tolist(),
            profit_factors=profit_factors.tolist(),
            mean_final_capital=float(np.mean(final_capitals)),
            std_final_capital=float(np.std(final_capitals)),
            median_final_capital=float(np.median(final_capitals)),
            percentile_5_final_capital=float(np.percentile(final_capitals, 5)),
            percentile_95_final_capital=float(np.percentile(final_capitals, 95)),
            mean_total_return=float(np.mean(total_returns)),
            std_total_return=float(np.std(total_returns)),
            mean_max_drawdown=float(np.mean(max_drawdowns)),
            max_max_drawdown=float(np.max(max_drawdowns)),
            mean_sharpe=float(np.mean(sharpe_ratios)),
            min_sharpe=float(np.min(sharpe_ratios)),
            max_sharpe=float(np.max(sharpe_ratios)),
            mean_win_rate=float(np.mean(win_rates)),
            prob_profit=float(np.mean(final_capitals > self.initial_capital) * 100),
            mean_profit_factor=float(np.mean(profit_factors)),
            best_run_capital=float(np.max(final_capitals)),
            worst_run_capital=float(np.min(final_capitals)),
        )


def run_monte_carlo(
    backtest_result: BacktestResult,
    num_simulations: int = 1000,
    num_bars: int | None = None,
    random_seed: int | None = 42,
) -> MonteCarloResult:
    """Convenience wrapper to run Monte Carlo from a BacktestResult."""
    simulator = MonteCarloSimulator(
        initial_capital=backtest_result.initial_capital,
        random_seed=random_seed,
    )
    return simulator.simulate(
        equity_curve=backtest_result.equity_curve,
        num_simulations=num_simulations,
        num_bars=num_bars,
    )