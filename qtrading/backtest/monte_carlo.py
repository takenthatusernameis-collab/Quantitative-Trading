from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
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

    def __init__(self, backtest_result: "BacktestResult", num_simulations: int = 1000):
        self.backtest_result = backtest_result
        self.num_simulations = num_simulations
        self.returns = self._extract_returns()

    def _extract_returns(self) -> np.ndarray:
        if self.backtest_result.equity_curve is None:
            return np.array([])

        equity = self.backtest_result.equity_curve["equity"].values
        returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
        return returns[~np.isnan(returns)]

    def simulate(
        self, num_days: int | None = None, confidence_intervals: tuple[float, float] = (0.05, 0.95)
    ) -> MonteCarloResult:
        if len(self.returns) == 0:
            raise ValueError("No returns data available for Monte Carlo simulation")

        num_days = (
            num_days
            if num_days is not None
            else len(self.backtest_result.equity_curve["equity"])
            if self.backtest_result.equity_curve is not None
            else 252
        )

        initial_capital = (
            float(self.backtest_result.initial_capital)
            if hasattr(self.backtest_result, "initial_capital")
            else 100000.0
        )
        if (
            self.backtest_result.equity_curve is not None
            and len(self.backtest_result.equity_curve) > 0
        ):
            initial_capital = float(self.backtest_result.equity_curve["equity"].iloc[0])

        rng = np.random.RandomState(42)
        final_capitals = []
        total_returns_list = []
        max_drawdowns_list = []
        sharpe_ratios_list = []
        win_rates_list = []
        profit_factors_list = []

        for _ in range(self.num_simulations):
            simulated_returns = rng.choice(self.returns, size=num_days, replace=True)
            capital_path = np.cumprod(1 + simulated_returns) * initial_capital
            final_capitals.append(float(capital_path[-1]))
            total_returns_list.append(float((capital_path[-1] / initial_capital) - 1))
            drawdowns = (capital_path / np.maximum.accumulate(capital_path)) - 1
            max_drawdowns_list.append(float(drawdowns.min()))
            sharpe_ratios_list.append(
                float(np.mean(simulated_returns) / np.std(simulated_returns) * np.sqrt(252))
                if np.std(simulated_returns) > 0
                else 0
            )
            win_rates_list.append(float(np.mean(simulated_returns > 0)))
            pos_returns = simulated_returns[simulated_returns > 0]
            neg_returns = simulated_returns[simulated_returns < 0]
            profit_factor = (
                float(np.sum(pos_returns) / abs(np.sum(neg_returns)))
                if len(neg_returns) > 0 and np.sum(neg_returns) != 0
                else float(np.sum(pos_returns))
                if len(pos_returns) > 0
                else 0
            )
            profit_factors_list.append(profit_factor)

        final_capitals_arr = np.array(final_capitals)
        total_returns_arr = np.array(total_returns_list)

        return MonteCarloResult(
            num_simulations=self.num_simulations,
            num_bars=num_days,
            initial_capital=initial_capital,
            final_capitals=final_capitals,
            total_returns=total_returns_list,
            max_drawdowns=max_drawdowns_list,
            sharpe_ratios=sharpe_ratios_list,
            win_rates=win_rates_list,
            profit_factors=profit_factors_list,
            mean_final_capital=float(np.mean(final_capitals_arr)),
            std_final_capital=float(np.std(final_capitals_arr)),
            median_final_capital=float(np.median(final_capitals_arr)),
            percentile_5_final_capital=float(
                np.percentile(final_capitals_arr, confidence_intervals[0] * 100)
            ),
            percentile_95_final_capital=float(
                np.percentile(final_capitals_arr, confidence_intervals[1] * 100)
            ),
            mean_total_return=float(np.mean(total_returns_arr)),
            std_total_return=float(np.std(total_returns_arr)),
            mean_max_drawdown=float(np.mean(max_drawdowns_list)),
            max_max_drawdown=float(np.min(max_drawdowns_list)),
            mean_sharpe=float(np.mean(sharpe_ratios_list)),
            min_sharpe=float(np.min(sharpe_ratios_list)),
            max_sharpe=float(np.max(sharpe_ratios_list)),
            mean_win_rate=float(np.mean(win_rates_list)),
            prob_profit=float(np.mean(np.array(final_capitals_arr) > initial_capital)),
            mean_profit_factor=float(np.mean(profit_factors_list)),
            best_run_capital=float(np.max(final_capitals_arr)),
            worst_run_capital=float(np.min(final_capitals_arr)),
        )
