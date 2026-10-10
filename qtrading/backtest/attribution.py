"""Benchmark comparison and performance attribution for backtest results."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BenchmarkComparison:
    benchmark_name: str
    strategy_return: float
    benchmark_return: float
    excess_return: float
    tracking_error: float
    information_ratio: float
    beta: float
    alpha: float
    up_capture: float
    down_capture: float


@dataclass
class PerformanceAttribution:
    symbol: str
    allocation_effect: float
    selection_effect: float
    interaction_effect: float
    total_effect: float
    benchmark_return: float


@dataclass
class AttributionResult:
    strategy_name: str
    benchmark_name: str
    total_allocation: float
    total_selection: float
    total_interaction: float
    total_attribution: float
    symbol_attributions: list[PerformanceAttribution] = field(default_factory=list)


class BenchmarkComparator:
    """Compares strategy performance against benchmarks."""

    def __init__(self, benchmark_data: dict[str, pd.DataFrame] | None = None):
        self.benchmark_data = benchmark_data or {}

    def add_benchmark(self, name: str, data: pd.DataFrame) -> None:
        self.benchmark_data[name] = data

    def compare(
        self,
        strategy_result,
        benchmark_name: str,
        benchmark_data: pd.DataFrame | None = None,
    ) -> BenchmarkComparison:
        data = benchmark_data or self.benchmark_data.get(benchmark_name)
        if data is None:
            raise ValueError(f"Benchmark '{benchmark_name}' not found")

        strat_returns = self._extract_returns(strategy_result)
        bench_returns = self._extract_benchmark_returns(data)

        common_idx = strat_returns.index.intersection(bench_returns.index)
        if len(common_idx) < 2:
            raise ValueError("Insufficient overlapping data")

        s = strat_returns.loc[common_idx]
        b = bench_returns.loc[common_idx]

        excess = s - b
        tracking_error = excess.std()
        information_ratio = excess.mean() / tracking_error if tracking_error > 0 else 0.0

        covariance = np.cov(s, b)[0, 1]
        bench_var = np.var(b)
        beta = covariance / bench_var if bench_var > 0 else 0.0

        risk_free = 0.0
        alpha = s.mean() - risk_free - beta * (b.mean() - risk_free)

        up_mask = b > 0
        down_mask = b < 0
        up_capture = 0.0
        down_capture = 0.0
        if up_mask.any() and b[up_mask].mean() != 0:
            up_capture = float(s[up_mask].mean() / b[up_mask].mean())
        if down_mask.any() and b[down_mask].mean() != 0:
            down_capture = float(s[down_mask].mean() / b[down_mask].mean())

        return BenchmarkComparison(
            benchmark_name=benchmark_name,
            strategy_return=float(s.sum()),
            benchmark_return=float(b.sum()),
            excess_return=float(excess.sum()),
            tracking_error=float(tracking_error),
            information_ratio=float(information_ratio),
            beta=float(beta),
            alpha=float(alpha),
            up_capture=float(up_capture),
            down_capture=float(down_capture),
        )

    def _extract_returns(self, strategy_result) -> pd.Series:
        if hasattr(strategy_result, "equity_curve") and strategy_result.equity_curve:
            equity = [float(v) for _, v in strategy_result.equity_curve]
            returns = pd.Series(equity).pct_change().dropna()
            return returns
        return pd.Series(dtype=float)

    def _extract_benchmark_returns(self, data: pd.DataFrame) -> pd.Series:
        if "close" in data.columns:
            return data["close"].pct_change().dropna()
        return pd.Series(dtype=float)


class PerformanceAttributor:
    """Performs performance attribution analysis (Brinson model)."""

    def __init__(self, benchmark_weights: dict[str, float] | None = None):
        self.benchmark_weights = benchmark_weights or {}

    def attribute(
        self,
        strategy_weights: dict[str, float],
        benchmark_weights: dict[str, float],
        strategy_returns: dict[str, float],
        benchmark_returns: dict[str, float],
        strategy_name: str = "Strategy",
        benchmark_name: str = "Benchmark",
    ) -> AttributionResult:
        all_symbols = set(strategy_weights.keys()) | set(benchmark_weights.keys())

        attributions = []
        total_alloc = 0.0
        total_sel = 0.0
        total_inter = 0.0

        for symbol in all_symbols:
            w_s = strategy_weights.get(symbol, 0.0)
            w_b = benchmark_weights.get(symbol, 0.0)
            r_s = strategy_returns.get(symbol, 0.0)
            r_b = benchmark_returns.get(symbol, 0.0)

            allocation = (w_s - w_b) * r_b
            selection = w_b * (r_s - r_b)
            interaction = (w_s - w_b) * (r_s - r_b)
            total_effect = allocation + selection + interaction

            total_alloc += allocation
            total_sel += selection
            total_inter += interaction

            attributions.append(
                PerformanceAttribution(
                    symbol=symbol,
                    allocation_effect=float(allocation),
                    selection_effect=float(selection),
                    interaction_effect=float(interaction),
                    total_effect=float(total_effect),
                    benchmark_return=float(r_b),
                )
            )

        return AttributionResult(
            strategy_name=strategy_name,
            benchmark_name=benchmark_name,
            total_allocation=float(total_alloc),
            total_selection=float(total_sel),
            total_interaction=float(total_inter),
            total_attribution=float(total_alloc + total_sel + total_inter),
            symbol_attributions=attributions,
        )


__all__ = [
    "BenchmarkComparison",
    "PerformanceAttribution",
    "AttributionResult",
    "BenchmarkComparator",
    "PerformanceAttributor",
]
