"""Seeded, randomized invariant tests for the cost and cash reconciliation.

The engine charges commission and slippage to cash on both sides of a trade and
capitalizes entry fees into the position cost basis. These tests drive the
engine with pseudo-random but fully deterministic scenarios (fixed seeds, no
network) and assert the accounting identities that must hold for *every* run:

1. ``BacktestResult.total_costs`` equals the sum of the per-trade fees.
2. The cash balance moved by exactly the signed trade costs (buys reduce cash,
   sells increase it).
3. The final portfolio value equals cash plus the market value of the open
   positions.
4. Realized plus unrealized PnL explains the change in portfolio value.
5. A fully liquidated run books all of its PnL as realized.
6. The trade log agrees with the portfolio on the quantity left in each symbol.
7. The trade analysis reports the PnL the run booked.

The scenarios cover full round trips, partial exits, adding to an existing
long position (weighted-average cost basis), multiple symbols, and runs where
the risk manager rejects a signal.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestEngine, BacktestResult
from quant_trading.backtest.metrics import calculate_backtest_metrics
from quant_trading.backtest.trade_analysis import analyze_trades
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.strategies.base import Signal, Strategy

INITIAL_CAPITAL = 10000.0


class _MockProvider(DataProvider):
    """Data provider that serves pre-built price frames without any network."""

    def __init__(self, data: dict[str, pd.DataFrame]):
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
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=self._data[symbol],
                    source=self.name,
                    fetched_at=datetime.now(),
                )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols: list) -> FetchResult:
        return self.fetch(symbols)


class _ScriptedStrategy(Strategy):
    """Emits a scripted sequence of ``(action, strength)`` signals, one per bar.

    The symbols are visited round-robin so that a single script can trade
    several instruments.
    """

    def __init__(self, script: list[tuple[str, float]], symbols: list[str]):
        super().__init__(name="Scripted")
        self._script = list(script)
        self._symbols = list(symbols)
        self._index = 0

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._index >= len(self._script):
            return []
        action, strength = self._script[self._index]
        symbol = self._symbols[self._index % len(self._symbols)]
        self._index += 1
        price = float(data[symbol]["close"].iloc[-1])
        return [Signal(symbol=symbol, action=action, strength=strength, price=price)]


def _make_price_series(prices: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    """Build an OHLC frame with a constant close price."""
    index = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [price * 1.01 for price in prices],
            "low": [price * 0.99 for price in prices],
            "close": prices,
        },
        index=index,
    )


def _make_data(symbols: list[str], bars: int, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Build random price frames for every symbol, all sharing one index."""
    data: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        prices = np.maximum(rng.uniform(50.0, 150.0, size=bars).round(2), 1.0).tolist()
        data[symbol] = _make_price_series(prices)
    return data


def _run_scenario(
    script: list[tuple[str, float]],
    data: dict[str, pd.DataFrame],
    commission: float,
    slippage: float,
    disable_risk: bool = False,
) -> tuple[BacktestResult, Portfolio]:
    """Run one scripted backtest and return the result and the final portfolio."""
    symbols = list(data.keys())
    provider = _MockProvider(data)
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        commission=commission,
        slippage=slippage,
    )
    engine = BacktestEngine(config=config, data_manager=DataManager([provider]))
    if disable_risk:
        engine.risk_manager.disable()
    engine.add_strategy(_ScriptedStrategy(script, symbols))
    index = next(iter(data.values())).index
    result = engine.run(
        symbols,
        index[0].to_pydatetime(),
        index[-1].to_pydatetime(),
        "1d",
    )
    return result, engine.portfolio


def _signed_cost(trades: pd.DataFrame) -> float:
    """Sum the trade costs with the sign that matches their effect on cash."""
    total = 0.0
    for _, trade in trades.iterrows():
        if trade["action"] in ("sell", "short"):
            total += trade["cost"]
        else:
            total -= trade["cost"]
    return total


def _assert_analysis_reconciles(result: BacktestResult) -> None:
    """Assert that the trade analysis reports the PnL the run booked.

    The engine books the fee of a short on the short row itself, so a run
    that ends with an open short booked a PnL that the completed round trips
    do not carry. The analysis has to report the PnL of the whole log, and
    the PnL of the symbols has to add up to it.
    """
    analysis = analyze_trades(result)
    booked = float(result.trades["pnl"].sum()) if not result.trades.empty else 0.0

    assert analysis.total_pnl == pytest.approx(booked, rel=1e-9, abs=1e-6)

    symbol_total = sum(stats["total_pnl"] for stats in (analysis.symbol_stats or {}).values())
    assert symbol_total == pytest.approx(analysis.total_pnl, rel=1e-9, abs=1e-6)

    # Metrics and analysis must agree on the PnL of the run
    metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
    assert metrics.total_pnl == pytest.approx(analysis.total_pnl, rel=1e-9, abs=1e-6)

    # The metrics the engine attached to the result are the same numbers.
    assert result.metrics.total_pnl == pytest.approx(analysis.total_pnl, rel=1e-9, abs=1e-6)


def _assert_cost_accounting_invariants(result: BacktestResult, portfolio: Portfolio) -> None:
    """Assert the cost and cash identities that hold for every backtest run."""
    trades = result.trades

    # 7. The trade analysis reports the PnL the run booked.
    _assert_analysis_reconciles(result)

    if trades.empty:
        # Nothing was traded, so nothing was charged and the value is unchanged.
        assert result.total_costs == 0.0
        assert result.final_value == pytest.approx(result.initial_capital, rel=1e-9, abs=1e-9)
        assert portfolio.holdings == {}
        return

    # 1. The headline cost figure is the sum of the per-trade fees.
    assert result.total_costs == pytest.approx(float(trades["fee"].sum()), rel=1e-9, abs=1e-9)

    signed_cost = _signed_cost(trades)

    # 2. Cash moved by exactly the signed trade costs.
    assert portfolio.cash - result.initial_capital == pytest.approx(signed_cost, rel=1e-9, abs=1e-6)

    # 3. The final value is cash plus the market value of the open positions.
    market_value = sum(holding.market_value for holding in portfolio.holdings.values())
    assert portfolio.cash + market_value == pytest.approx(result.final_value, rel=1e-9, abs=1e-6)

    # 4. Realized plus unrealized PnL explains the change in portfolio value.
    realized = float(trades["pnl"].sum())
    unrealized = sum(holding.unrealized_pnl for holding in portfolio.holdings.values())
    assert result.final_value - result.initial_capital == pytest.approx(
        realized + unrealized, rel=1e-9, abs=1e-6
    )

    # 5. A fully liquidated run books all of its PnL as realized.
    if not portfolio.holdings:
        assert realized == pytest.approx(
            result.final_value - result.initial_capital, rel=1e-9, abs=1e-6
        )

    # 6. The trade log agrees with the portfolio on the quantity left per symbol.
    for symbol in {trade["symbol"] for _, trade in trades.iterrows()}:
        net = 0.0
        for _, trade in trades.iterrows():
            if trade["symbol"] != symbol:
                continue
            if trade["action"] in ("buy", "cover"):
                net += trade["quantity"]
            else:
                net -= trade["quantity"]
        held = portfolio.holdings[symbol].quantity if symbol in portfolio.holdings else 0.0
        assert net == pytest.approx(held, rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("seed", range(20))
def test_randomized_round_trip_invariants(seed: int):
    """A single long position exited in random partial steps reconciles."""
    rng = np.random.default_rng(seed)
    partial_sells = int(rng.integers(1, 4))
    strengths = [float(value) for value in rng.uniform(0.1, 0.9, size=partial_sells)]
    script = [("buy", 1.0)] + [("sell", strength) for strength in strengths]
    script.append(("sell", 1.0))

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage)

    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_randomized_add_to_existing_position_invariants(seed: int):
    """Adding to an open long keeps the weighted-average cost basis consistent."""
    rng = np.random.default_rng(seed)
    partial_sells = int(rng.integers(1, 3))
    strengths = [float(value) for value in rng.uniform(0.2, 0.8, size=partial_sells)]
    script = [("buy", 0.4), ("buy", 1.0)]
    script += [("sell", strength) for strength in strengths]
    script.append(("sell", 1.0))

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    # Risk checks are disabled so the second buy is not rejected by the
    # position limit; the trade accounting itself is unaffected.
    result, portfolio = _run_scenario(script, data, commission, slippage, disable_risk=True)

    assert len(result.trades) == len(script)
    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_randomized_multiple_symbol_invariants(seed: int):
    """A run that trades two symbols reconciles symbol by symbol."""
    rng = np.random.default_rng(seed)
    symbols = ["AAA", "BBB"]
    script = [
        ("buy", 0.6),
        ("buy", 0.6),
        ("sell", 0.5),
        ("sell", 0.5),
        ("sell", 1.0),
        ("sell", 1.0),
    ]

    data = _make_data(symbols, len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage, disable_risk=True)

    assert set(result.trades["symbol"]) == set(symbols)
    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_randomized_risk_enabled_invariants(seed: int):
    """Runs where the risk manager rejects signals still reconcile."""
    rng = np.random.default_rng(seed)
    strengths = [float(value) for value in rng.uniform(0.2, 0.9, size=2)]
    script = [("buy", 1.0)]
    script += [("sell", strength) for strength in strengths]
    script.append(("sell", 1.0))

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage)

    _assert_cost_accounting_invariants(result, portfolio)


def test_sell_signal_larger_than_position_records_executed_quantity():
    """A sell signal with ``strength > 1`` closes only the position it holds.

    The portfolio caps the removal at the position size, so the trade log has
    to record the executed quantity as well; otherwise the realized PnL and the
    cash balance disagree with the trade log.
    """
    rng = np.random.default_rng(7)
    script = [("buy", 1.0), ("sell", 1.5)]
    data = _make_data(["TEST"], len(script) + 2, rng)

    result, portfolio = _run_scenario(
        script, data, commission=0.001, slippage=0.0005, disable_risk=True
    )

    assert len(result.trades) == 2
    buy = result.trades[result.trades["action"] == "buy"].iloc[0]
    sell = result.trades[result.trades["action"] == "sell"].iloc[0]

    # The whole position was sold, and the log says exactly that.
    assert sell["quantity"] == pytest.approx(buy["quantity"], rel=1e-9, abs=1e-9)
    assert portfolio.holdings == {}

    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(20))
def test_randomized_short_round_trip_invariants(seed: int):
    """A short position covered in random partial steps reconciles.

    A short keeps the raw execution price as its cost basis, so the entry fee
    it pays is booked as realized PnL on the short trade itself. The covers
    book the price move and the cover fee. The sum of the two is the change in
    the portfolio value, exactly like it is for a long.
    """
    rng = np.random.default_rng(seed)
    partial_covers = int(rng.integers(1, 4))
    strengths = [float(value) for value in rng.uniform(0.1, 0.3, size=partial_covers)]
    script = [("short", 1.0)] + [("buy", strength) for strength in strengths]
    script.append(("buy", 1.0))

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage)

    # The short was opened and then covered, and the position is flat again.
    assert not result.trades.empty
    assert (result.trades["action"] == "short").sum() == 1
    assert (result.trades["action"] == "cover").sum() == len(script) - 1
    assert portfolio.holdings == {}

    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_randomized_open_short_invariants(seed: int):
    """A short that is never covered still reconciles while it is open."""
    rng = np.random.default_rng(seed)
    script = [("short", 1.0)]

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage)

    assert len(result.trades) == 1
    assert portfolio.holdings["TEST"].quantity < 0

    _assert_cost_accounting_invariants(result, portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_randomized_short_against_an_open_long_invariants(seed: int):
    """A short signal against an open long is rejected, and the log reconciles.

    A short never flips a position, so the signal is rejected: the long stays
    open and the trade log keeps agreeing with the portfolio. Without that
    rule the engine books a short that the portfolio turned into a sale of
    the long, so the log would report a position and a PnL the portfolio
    never had.
    """
    rng = np.random.default_rng(seed)
    script = [("buy", 0.3), ("short", 1.0)]

    data = _make_data(["TEST"], len(script) + 2, rng)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))

    result, portfolio = _run_scenario(script, data, commission, slippage, disable_risk=True)

    # The short was rejected, so only the buy is in the log.
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["action"] == "buy"
    assert portfolio.holdings["TEST"].quantity > 0

    _assert_cost_accounting_invariants(result, portfolio)
