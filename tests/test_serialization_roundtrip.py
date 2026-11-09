"""Cross-cutting serialization round-trip tests.

Iterates every serializable dataclass's ``to_dict()``/``from_dict()`` pair and
asserts ``from_dict(to_dict(x)) == x`` to catch serialization drift early now
that the ``to_dict``/``from_dict`` pattern covers every dataclass in the repo.

Classes whose ``to_dict()`` deliberately omits pandas-backed state
(``BacktestResult`` drops ``equity_curve``/``trades``/``positions``;
``BacktestRegimeAnalysis`` drops ``equity_curve``) are intentionally excluded:
their dataclass ``__eq__`` cannot compare the omitted fields, so a field
equality round-trip is not meaningful. They remain covered by their own
per-class serialization tests (e.g. ``TestBacktestResultSerialization``).
"""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.trade_analysis import TradeAnalysis
from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)
from quant_trading.monte_carlo.simulator import MonteCarloResult
from quant_trading.optimization.base import OptimizationResult
from quant_trading.optimization.bayesian import BayesianOptimizerConfig
from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow
from quant_trading.portfolio.portfolio import Holding, Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, RebalanceExecution
from quant_trading.regime.detector import Regime, RegimeResult, RegimeSegment
from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
from quant_trading.risk.manager import PortfolioRisk
from quant_trading.risk.metrics import RiskMetrics
from quant_trading.strategies.base import Position, Signal


def _instances():
    ts = datetime(2024, 1, 1, 12, 0, 0)
    metrics = BacktestMetrics()
    segment = RegimeSegment(
        regime=Regime.UNKNOWN,
        start=pd.Timestamp("2024-01-01"),
        end=pd.Timestamp("2024-01-02"),
        start_index=0,
        end_index=1,
        volatility=0.1,
        return_pct=0.05,
    )
    window = WalkForwardWindow(
        train_start=datetime(2024, 1, 1),
        train_end=datetime(2024, 2, 1),
        test_start=datetime(2024, 2, 1),
        test_end=datetime(2024, 3, 1),
        best_params={"fast": 5},
    )
    return [
        (DataConfig, DataConfig()),
        (BacktestConfig, BacktestConfig()),
        (RiskConfig, RiskConfig()),
        (PortfolioConfig, PortfolioConfig()),
        (Config, Config()),
        (
            MonteCarloResult,
            MonteCarloResult(
                simulations=[metrics],
                original_metrics=metrics,
                n_simulations=1,
                confidence_level=0.95,
                start_time=datetime(2024, 1, 1),
                end_time=datetime(2024, 1, 2),
            ),
        ),
        (Signal, Signal(symbol="AAPL", action="buy", timestamp=ts, metadata={"key": "value"})),
        (Position, Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=160.0)),
        (WalkForwardWindow, window),
        (WalkForwardResult, WalkForwardResult(windows=[window])),
        (OptimizationResult, OptimizationResult(best_params={"x": 1}, best_score=1.0)),
        (BayesianOptimizerConfig, BayesianOptimizerConfig()),
        (RebalanceAction, RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)),
        (RebalanceExecution, RebalanceExecution(symbol="AAPL", action="buy", requested_quantity=10.0)),
        (RegimeSegment, segment),
        (RegimeResult, RegimeResult(
            segments=[segment],
            regimes=[segment.regime],
            n_segments=1,
            current_regime=segment.regime,
        )),
        (Holding, Holding(symbol="AAPL", quantity=100, avg_cost=150.0, current_price=160.0)),
        (
            Portfolio,
            Portfolio(
                cash=10000.0,
                total_value=10000.0,
                holdings={"AAPL": Holding(symbol="AAPL")},
            ),
        ),
        (BacktestMetrics, metrics),
        (TradeAnalysis, TradeAnalysis()),
        (RiskMetrics, RiskMetrics()),
        (PortfolioRisk, PortfolioRisk()),
        (PositionLimit, PositionLimit()),
        (PortfolioLimit, PortfolioLimit()),
        (CheckResult, CheckResult(passed=True)),
    ]


@pytest.mark.parametrize(
    "cls,instance",
    _instances(),
    ids=[cls.__name__ for cls, _ in _instances()],
)
def test_serialization_round_trip(cls, instance):
    """Every serializable class must round-trip through to_dict/from_dict."""
    restored = cls.from_dict(instance.to_dict())
    assert restored == instance
