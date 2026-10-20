"""Seeded, randomized invariant tests for cost and cash reconciliation.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestEngine, Trade
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.strategies.base import Signal, Strategy


class MockDataProvider(DataProvider):
    def __init__(self, data: dict):
        self._data = data
        self._name = "mock"

    @property
    def name(self) -> str:
        return self._name

    def fetch(
        self,
        symbols: list,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        result = FetchResult()
        for symbol in symbols:
            if symbol in self._data:
                df = self._data[symbol]
                if start and end:
                    mask = (df.index >= start) & (df.index <= end)
                    result.data[symbol] = MarketData(
                        symbol=symbol, data=df.loc[mask], source=self.name, fetched_at=datetime.now()
                    )
                else:
                    result.data[symbol] = MarketData(
                        symbol=symbol, data=df.copy(), source=self.name, fetched_at=datetime.now()
                    )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols: list) -> FetchResult:
        return self.fetch(symbols)

    def get_historical_data(self, symbol, start, end, interval="1d"):
        if symbol in self._data:
            df = self._data[symbol]
            mask = (df.index >= start) & (df.index <= end)
            return df.loc[mask]
        return pd.DataFrame()


def _make_price_series(prices, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
        },
        index=idx,
    )

@pytest.mark.parametrize("seed", [12345, 23456, 34567, 45678, 56789])
def test_cost_accounting_invariants_randomized_round_trips(seed):
    rng = np.random.default_rng(seed)
    n_bars = 10
    base_price = 100.0
    prices = base_price * np.exp(rng.normal(0, 0.01, n_bars)).cumprod()
    prices = np.maximum(prices, 1.0)
    commission = rng.uniform(0.0001, 0.02)
    slippage = rng.uniform(0.0001, 0.01)
    data = {"TEST": _make_price_series(prices)}
    idx = list(data["TEST"].index)
    initial_capital = 100000.0
    provider = MockDataProvider(data)
    config = BacktestConfig(initial_capital=initial_capital, commission=commission, slippage=slippage)
    class BuySellStrategy(Strategy):
        def __init__(self, sell_ratio):
            super().__init__("bs")
            self.sell_ratio = sell_ratio
            self.bought = False
        def generate_signals(self, data):
            signals = []
            for symbol, df in data.items():
                for i, date_idx in enumerate(df.index):
                    if i == 2 and not self.bought:
                        signals.append(Signal(symbol=symbol, action="buy", strength=1.0))
                        self.bought = True
                    elif i == 5:
                        signals.append(Signal(symbol=symbol, action="sell", strength=self.sell_ratio))
            return signals
    sell_ratio = rng.uniform(0.5, 1.0)
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(BuySellStrategy(sell_ratio))
    result = engine.run(["TEST"], idx[0], idx[-1])
    if not result.trades.empty:
        assert result.total_costs == pytest.approx(result.trades["fee"].sum())
        signed_cost = 0.0
        for _, trade in result.trades.iterrows():
            if trade["action"] == "sell":
                signed_cost += trade["cost"]
            else:
                signed_cost -= trade["cost"]
        assert result.final_value - result.initial_capital == pytest.approx(signed_cost)
    if len(result.positions) == 0 and not result.trades.empty:
        assert result.trades["pnl"].sum() == pytest.approx(result.final_value - result.initial_capital)

@pytest.mark.parametrize("seed", [111, 222, 333, 444, 555])
def test_cost_accounting_partial_sells(seed):
    rng = np.random.default_rng(seed)
    n_bars = 15
    prices = 100.0 * np.ones(n_bars)
    for i in range(1, n_bars):
        prices[i] = prices[i-1] * (1 + rng.normal(0, 0.005))
    prices = np.maximum(prices, 1.0)
    commission = rng.uniform(0.001, 0.005)
    slippage = rng.uniform(0.001, 0.003)
    data = {"TEST": _make_price_series(prices)}
    idx = list(data["TEST"].index)
    initial_capital = 50000.0
    provider = MockDataProvider(data)
    config = BacktestConfig(initial_capital=initial_capital, commission=commission, slippage=slippage)
    class MultiSell(Strategy):
        def __init__(self):
            super().__init__("ms")
            self.bought = False
            self.step = 0
        def generate_signals(self, data):
            signals = []
            for symbol, df in data.items():
                for i, date_idx in enumerate(df.index):
                    if i == 1 and not self.bought:
                        signals.append(Signal(symbol=symbol, action="buy", strength=1.0))
                        self.bought = True
                    elif i == 3 and self.step == 0:
                        signals.append(Signal(symbol=symbol, action="sell", strength=0.3))
                        self.step = 1
                    elif i == 6 and self.step == 1:
                        signals.append(Signal(symbol=symbol, action="sell", strength=0.4))
                        self.step = 2
                    elif i == 10 and self.step == 2:
                        signals.append(Signal(symbol=symbol, action="sell", strength=1.0))
                        self.step = 3
            return signals
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(MultiSell())
    result = engine.run(["TEST"], idx[0], idx[-1])
    if not result.trades.empty:
        assert result.total_costs == pytest.approx(result.trades["fee"].sum())
        signed_cost = 0.0
        for _, trade in result.trades.iterrows():
            if trade["action"] == "sell":
                signed_cost += trade["cost"]
            else:
                signed_cost -= trade["cost"]
        assert result.final_value - result.initial_capital == pytest.approx(signed_cost)
    if len(result.positions) == 0 and not result.trades.empty:
        assert result.trades["pnl"].sum() == pytest.approx(result.final_value - result.initial_capital)

@pytest.mark.parametrize("seed", [777, 888, 999])
def test_cost_accounting_multiple_symbols(seed):
    rng = np.random.default_rng(seed)
    symbols = ["AAPL", "MSFT"]
    data = {}
    idx = pd.date_range("2024-01-01", periods=8, freq="D")
    for sym in symbols:
        prices = 100.0 + rng.normal(0, 5, 8).cumsum()
        prices = np.maximum(prices, 10.0)
        data[sym] = pd.DataFrame(
            {"open": prices, "high": prices * 1.02, "low": prices * 0.98, "close": prices},
            index=idx,
        )
    commission = 0.001
    slippage = 0.0005
    provider = MockDataProvider(data)
    config = BacktestConfig(initial_capital=200000.0, commission=commission, slippage=slippage)
    class MultiSym(Strategy):
        def __init__(self):
            super().__init__("multisym")
        def generate_signals(self, data):
            signals = []
            for symbol, df in data.items():
                for i, date_idx in enumerate(df.index):
                    if symbol == "AAPL" and i == 1:
                        signals.append(Signal(symbol=symbol, action="buy", strength=1.0))
                    elif symbol == "MSFT" and i == 2:
                        signals.append(Signal(symbol=symbol, action="buy", strength=1.0))
                    elif symbol == "AAPL" and i == 5:
                        signals.append(Signal(symbol=symbol, action="sell", strength=1.0))
                    elif symbol == "MSFT" and i == 6:
                        signals.append(Signal(symbol=symbol, action="sell", strength=1.0))
            return signals
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    engine.add_strategy(MultiSym())
    result = engine.run(symbols, idx[0], idx[-1])
    if not result.trades.empty:
        assert result.total_costs == pytest.approx(result.trades["fee"].sum())
        signed_cost = 0.0
        for _, trade in result.trades.iterrows():
            if trade["action"] == "sell":
                signed_cost += trade["cost"]
            else:
                signed_cost -= trade["cost"]
        assert result.final_value - result.initial_capital == pytest.approx(signed_cost)
        if len(result.positions) == 0:
            assert result.trades["pnl"].sum() == pytest.approx(result.final_value - result.initial_capital)
