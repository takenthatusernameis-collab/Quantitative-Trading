"""Cross-cutting serialization round-trip tests.

Discovers serializable dataclasses (``to_dict()``/``from_dict()``) and asserts a
stable serialization round-trip to catch drift.

For most classes this is full object equality: ``from_dict(to_dict(x)) == x``.
A few classes deliberately omit pandas-backed runtime state from ``to_dict()``
(``BacktestResult`` drops ``equity_curve``/``trades``/``positions``;
``BacktestRegimeAnalysis`` drops ``equity_curve``), so their dataclass ``__eq__``
cannot compare the omitted fields meaningfully. For those we assert serialized-
form stability instead: ``from_dict(to_dict(x)).to_dict() == x.to_dict()``.
"""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest.analysis import BacktestRegimeAnalysis
from quant_trading.backtest.engine import BacktestResult, Trade
from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.trade_analysis import TradeAnalysis
from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)
from quant_trading.data.providers import FetchResult, MarketData
from quant_trading.monte_carlo.simulator import MonteCarloResult
from quant_trading.optimization.base import OptimizationResult, ParameterGrid, ParameterSpace
from quant_trading.optimization.bayesian import BayesianOptimizerConfig
from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow
from quant_trading.portfolio.portfolio import Holding, Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, RebalanceExecution
from quant_trading.regime.detector import Regime, RegimeResult, RegimeSegment
from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
from quant_trading.risk.manager import PortfolioRisk
from quant_trading.risk.metrics import RiskMetrics
from quant_trading.strategies.base import Position, Signal

# Classes whose to_dict() omits or transforms runtime state (pandas/exception
# objects) so dataclass __eq__ is not meaningful: compare serialized form.
_DICT_STABLE = {BacktestResult, BacktestRegimeAnalysis, MarketData, FetchResult}


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
    regime_result = RegimeResult(
        segments=[segment],
        regimes=[segment.regime],
        n_segments=1,
        current_regime=segment.regime,
    )
    window = WalkForwardWindow(
        train_start=datetime(2024, 1, 1),
        train_end=datetime(2024, 2, 1),
        test_start=datetime(2024, 2, 1),
        test_end=datetime(2024, 3, 1),
        best_params={"fast": 5},
    )
    backtest_result = BacktestResult(
        equity_curve=pd.Series(dtype=float),
        trades=pd.DataFrame(),
        positions=pd.DataFrame(),
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 2),
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )
    regime_analysis = BacktestRegimeAnalysis(
        result=regime_result,
        equity_curve=pd.Series(dtype=float),
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
        (Trade, Trade(symbol="AAPL", action="buy", quantity=100, price=150.0, timestamp=ts)),
        (WalkForwardWindow, window),
        (WalkForwardResult, WalkForwardResult(windows=[window])),
        (OptimizationResult, OptimizationResult(best_params={"x": 1}, best_score=1.0)),
        (BayesianOptimizerConfig, BayesianOptimizerConfig()),
        (
            ParameterSpace,
            ParameterSpace(name="fast", values=[5, 10, 15]),
        ),
        (
            ParameterGrid,
            ParameterGrid().add(ParameterSpace(name="fast", values=[5, 10, 15])),
        ),
        (RebalanceAction, RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)),
        (RebalanceExecution, RebalanceExecution(symbol="AAPL", action="buy", requested_quantity=10.0)),
        (
            MarketData,
            MarketData(
                symbol="AAPL",
                data=pd.DataFrame(
                    {"close": [100.0, 101.0]},
                    index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
                ),
                source="synthetic",
                fetched_at=datetime(2024, 1, 1, 12, 0, 0),
                metadata={"interval": "1d"},
            ),
        ),
        (
            FetchResult,
            FetchResult(
                data={
                    "AAPL": MarketData(
                        symbol="AAPL",
                        data=pd.DataFrame({"close": [100.0]}),
                        source="synthetic",
                        fetched_at=datetime(2024, 1, 1),
                    )
                },
                errors={"MSFT": RuntimeError("boom")},
                missing=["GOOG"],
            ),
        ),
        (RegimeSegment, segment),
        (RegimeResult, regime_result),
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
        (BacktestResult, backtest_result),
        (BacktestRegimeAnalysis, regime_analysis),
    ]


@pytest.mark.parametrize(
    "cls,instance",
    _instances(),
    ids=[cls.__name__ for cls, _ in _instances()],
)
def test_serialization_round_trip(cls, instance):
    """Serializable dataclasses must round-trip through to_dict/from_dict."""
    restored = cls.from_dict(instance.to_dict())
    if cls in _DICT_STABLE:
        assert restored.to_dict() == instance.to_dict()
    else:
        assert restored == instance
