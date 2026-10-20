"""Seeded, randomized invariant tests for cost/cash reconciliation."""

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.strategies.base import Signal, Strategy


class _MockProvider(DataProvider):
    def __init__(self, data):
        self._data = data
        self._name = "mock"

    @property
    def name(self):
        return self._name

    def fetch(self, symbols, start=None, end=None, interval="1d"):
        result = FetchResult()
        for symbol in symbols:
            if symbol in self._data:
                result.data[symbol] = MarketData(
                    symbol=symbol, data=self._data[symbol], source=self.name, fetched_at=None
                )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols):
        return self.fetch(symbols)


class _ScriptedStrategy(Strategy):
    """Buys on the first bar, then sells per the given strength sequence."""

    def __init__(self, sell_strengths):
        super().__init__(name="Scripted")
        self._sell_strengths = list(sell_strengths)
        self._i = 0
        self._bought = False

    def generate_signals(self, data):
        symbol, df = next(iter(data.items()))
        price = float(df["close"].iloc[-1])
        if not self._bought:
            self._bought = True
            return [Signal(symbol=symbol, action="buy", strength=1.0, price=price)]
        if self._i < len(self._sell_strengths):
            s = self._sell_strengths[self._i]
            self._i += 1
            return [Signal(symbol=symbol, action="sell", strength=s, price=price)]
        return []


def _run(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(4, 9))
    prices = rng.uniform(50, 150, size=n).round(2)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    data = {
        "TEST": pd.DataFrame(
            {
                "open": prices,
                "high": prices + 1,
                "low": prices - 1,
                "close": prices,
            },
            index=idx,
        )
    }
    # intermediate partial sells, final full liquidation
    k = int(rng.integers(1, 4))
    strengths = [float(x) for x in rng.uniform(0.1, 0.9, size=k)]
    strengths.append(1.0)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    provider = _MockProvider(data)
    config = BacktestConfig(initial_capital=10000.0, commission=commission, slippage=slippage)
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(_ScriptedStrategy(strengths))
    start = idx[0].to_pydatetime()
    end = idx[-1].to_pydatetime()
    result = engine.run(["TEST"], start, end, "1d")
    return result, engine


@pytest.mark.parametrize("seed", range(20))
def test_cost_accounting_invariants(seed):
    result, engine = _run(seed)
    trades = result.trades
    assert result.total_costs == pytest.approx(float(trades["fee"].sum()))
    signed = 0.0
    for _, t in trades.iterrows():
        if t["action"] == "buy":
            signed -= float(t["cost"])
        else:
            signed += float(t["cost"])
    assert engine.portfolio.cash - result.initial_capital == pytest.approx(signed)
    positions = engine.portfolio.holdings
    if not positions:
        assert result.final_value - result.initial_capital == pytest.approx(signed)
        assert float(trades["pnl"].sum()) == pytest.approx(
            result.final_value - result.initial_capital
        )
    mv = sum(h.quantity * h.current_price for h in positions.values())
    assert engine.portfolio.cash + mv == pytest.approx(result.final_value)
