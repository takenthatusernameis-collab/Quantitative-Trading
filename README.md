# Quantitative Trading Framework

A modular Python framework for algorithmic trading strategies, backtesting, and portfolio management.

## Features

- **Strategy Framework**: Abstract base class for creating custom trading strategies
- **Built-in Strategies**: 46 registered strategies — Moving Average Crossover, EMA Crossover, RSI Mean Reversion, Stochastic RSI, Bollinger Bands, MACD, SuperTrend, Donchian Channel, Ease of Movement, Aroon, Keltner Channel, Stochastic Oscillator, Ichimoku Cloud, Hull Moving Average, Parabolic SAR, VWAP, Vortex, Awesome Oscillator, Momentum, ADX, Commodity Channel Index, Williams %R, On-Balance Volume, Chaikin Money Flow, Force Index, Money Flow Index, Elder Ray, Rate of Change, Volume Rate of Change, Volume Oscillator, Volume Price Trend, Percentage Price Oscillator, Percentage Volume Oscillator, Chande Momentum Oscillator, Chaikin Oscillator, TRIX, Accumulation Distribution, Negative Volume Index, Positive Volume Index, Ultimate Oscillator, Detrended Price Oscillator, Stochastic Momentum Index, Average True Range Channel Breakout, and Volume Weighted Average Price (VWAP) variations/others present as implemented
- **Backtesting Engine**: Event-driven backtest with realistic costs (commission, slippage), long and short positions
- **Data Providers**: Yahoo Finance integration with caching support plus an offline synthetic data provider (`SyntheticDataProvider`, `create_synthetic_data`, `create_synthetic_provider`)
- **Portfolio Management**: Position tracking, rebalancing, and allocation
- **Risk Management**: Position limits, portfolio limits, stop-loss/take-profit
- **Performance Metrics**: Sharpe, Sortino, Calmar ratios, max drawdown, VaR, win rate, profit factor
- **Market Regime Detection**: Classify equity curves into bull/bear/sideways regimes (low/high volatility)
- **Monte Carlo Simulation**: Bootstrap and parametric simulation of backtest outcomes
- **Parameter Optimization**: Grid search, random search, Bayesian optimization, and walk-forward analysis
- **Configuration**: YAML-based configuration system

## Installation

```bash
pip install -r requirements.txt
# Or for development:
pip install -e ".[dev]"
```

## Quick Start

```python
from datetime import datetime, timedelta
from quant_trading.backtest.engine import run_backtest
from quant_trading.strategies.examples import MovingAverageCrossover

# Define strategy
strategy = MovingAverageCrossover(fast_period=10, slow_period=30)

# Run backtest
end_date = datetime.now()
start_date = end_date - timedelta(days=365)

result = run_backtest(
    strategy=strategy,
    symbols=["AAPL", "MSFT", "GOOGL"],
    start=start_date,
    end=end_date,
    initial_capital=100000.0,
)

print(f"Total Return: {result.total_return_pct:.2f}%")
print(f"Trading Costs: {result.total_costs:.2f}")
print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")
print(f"Unrealized PnL: {result.metrics.unrealized_pnl:.2f}")
```

## Project Structure

```
quant_trading/
├── strategies/          # Trading strategies
│   ├── base.py         # Base classes (Strategy, Signal, Position)
│   ├── examples.py     # Built-in strategies
│   └── factory.py      # Strategy registry and factory
├── backtest/           # Backtesting engine
│   ├── engine.py       # Main backtest engine
│   ├── metrics.py      # Performance metrics
│   ├── analysis.py     # Regime and trade analysis helpers
│   └── trade_analysis.py # Detailed trade-level analysis
├── data/               # Data providers
│   ├── providers.py    # Base interfaces
│   ├── synthetic.py    # Deterministic synthetic data generator
│   └── yfinance_provider.py  # Yahoo Finance implementation
├── portfolio/          # Portfolio management
│   ├── portfolio.py    # Portfolio and holdings
│   └── rebalancer.py   # Rebalancing logic
├── risk/               # Risk management
│   ├── limits.py       # Position/portfolio limits
│   ├── manager.py      # Risk manager
│   └── metrics.py      # Risk metrics
├── optimization/       # Parameter optimization
│   ├── base.py         # Base classes and objective functions
│   ├── grid_search.py  # Exhaustive grid search
│   ├── random_search.py# Randomized search
│   ├── bayesian.py     # Bayesian optimization
│   └── walk_forward.py # Walk-forward analysis
├── monte_carlo/        # Monte Carlo simulation
│   └── simulator.py    # Bootstrap and parametric simulation
├── regime/             # Market regime detection
│   └── detector.py     # Bull/bear/sideways regime classification
├── config/             # Configuration
│   └── settings.py     # Config classes
└── utils/              # Utilities
    ├── formatting.py   # Number formatting
    └── logging.py      # Logging setup
```

## Strategy Registry

Strategies can be registered in a global registry and created dynamically by
key, with optional aliases. The built-in strategies are pre-registered:

- `ma` (aliases: `moving_average`, `ma_crossover`) → `MovingAverageCrossover`
- `rsi` (alias: `rsi_mean_reversion`) → `RSIStrategy`
- `bb` (aliases: `bollinger_bands`, `bollinger`) → `BollingerBandsStrategy`
- `bbpct` (aliases: `bollinger_bands_pct`, `percent_b`) → `BollingerPercentBStrategy`
- `macd` (alias: `macd_crossover`) → `MACDStrategy`
- `ema` (aliases: `ema_crossover`, `exponential_ma_crossover`) → `EMACrossover`
- `eom` (aliases: `ease_of_movement`) → `EaseOfMovementStrategy`
- `supertrend` (aliases: `st`, `super_trend`) → `SuperTrendStrategy`
- `donchian` (aliases: `donchian_channel`, `dc`) → `DonchianChannelStrategy`
- `aroon` (alias: `aroon_oscillator`) → `AroonStrategy`
- `keltner` (aliases: `kc`, `keltner_channel`) → `KeltnerChannelStrategy`
- `stoch` (aliases: `stochastic`, `stoch_oscillator`) → `StochasticOscillatorStrategy`
- `stochrsi` (aliases: `stochastic_rsi`, `stoch_rsi`) → `StochRSIStrategy`
- `ichimoku` (alias: `ichimoku_cloud`) → `IchimokuCloudStrategy`
- `klinger` (aliases: `klinger_oscillator`) → `KlingerOscillatorStrategy`
- `hma` (alias: `hull_moving_average`) → `HullMovingAverageStrategy`
- `sar` (aliases: `parabolic_sar`, `psar`) → `ParabolicSARStrategy`
- `vwap` → `VWAPStrategy`
- `vortex` (alias: `vortex_indicator`) → `VortexStrategy`
- `vpt` (alias: `volume_price_trend`) → `VolumePriceTrendStrategy`
- `chop` (aliases: `choppiness`, `choppiness_index`) → `ChoppinessIndexStrategy`
- `vroc` (alias: `volume_rate_of_change`) → `VolumeRateOfChangeStrategy`
- `ao` (alias: `awesome_oscillator`) → `AwesomeOscillatorStrategy`
- `vol` (alias: `volume_oscillator`) → `VolumeOscillatorStrategy`
- `ppo` (aliases: `percentage_price_oscillator`, `ppo_strategy`) → `PercentagePriceOscillatorStrategy`
- `pvo` (aliases: `percentage_volume_oscillator`, `pvo_strategy`) → `PercentageVolumeOscillatorStrategy`
- `cho` (alias: `chaikin_oscillator`) → `ChaikinOscillatorStrategy`
- `cmo` (alias: `chande_momentum_oscillator`) → `ChandeMomentumOscillatorStrategy`
- `momentum` (alias: `mom`) → `MomentumStrategy`
- `adx` (alias: `average_directional_index`) → `ADXStrategy`
- `atr` (aliases: `average_true_range`, `atr_channel`) → `AverageTrueRangeStrategy`
- `cci` (alias: `commodity_channel_index`) → `CCIStrategy`
- `williamsr` (alias: `williams_pct_r`) → `WilliamsRStrategy`
- `obv` (alias: `on_balance_volume`) → `OBVStrategy`
- `nvi` (alias: `negative_volume_index`) → `NegativeVolumeIndexStrategy`
- `pvi` (alias: `positive_volume_index`) → `PositiveVolumeIndexStrategy`
- `cmf` (alias: `chaikin_money_flow`) → `ChaikinMoneyFlowStrategy`
- `force_index` (aliases: `forceindex`, `fi`) → `ForceIndexStrategy`
- `mfi` (alias: `money_flow_index`) → `MoneyFlowIndexStrategy`
- `roc` (alias: `rate_of_change`) → `RateOfChangeStrategy`
- `trix` → `TrixStrategy`
- `ultimate_oscillator` (aliases: `uo`, `ultimate`) → `UltimateOscillatorStrategy`
- `dpo` (aliases: `detrended_price_oscillator`) → `DetrendedPriceOscillatorStrategy`
- `smi` (aliases: `stochastic_momentum_index`) → `StochasticMomentumIndexStrategy`
- `elder_ray` (aliases: `elder_ray_index`, `erp`) → `ElderRayStrategy`
- `adl` (aliases: `accumulation_distribution`, `ad_line`) → `AccumulationDistributionStrategy`

```python
from quant_trading.strategies import (
    MovingAverageCrossover,
    create_strategy,
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_keys,
)

# Create a built-in strategy by key or alias
strategy = create_strategy("ma", fast_period=5, slow_period=20)
assert get_strategy("ma_crossover") is MovingAverageCrossover

# Register a custom strategy (optionally with aliases)
register_strategy("my_strategy", MyStrategy, aliases=["my_algo"])
custom = create_strategy("my_strategy")

print(strategy_keys())     # primary keys + aliases
print(list_strategies())   # primary keys -> classes
```

`Strategy.from_config(config)` also resolves strategies through the registry:

```python
strategy = Strategy.from_config({
    "type": "rsi",
    "name": "MyRSI",
    "parameters": {"period": 21, "oversold": 25, "overbought": 75},
})
```

## Running Tests

```bash
# Full suite: unit tests plus the doctests embedded in quant_trading/
pytest -v
```

## Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy quant_trading/

# Formatting
black quant_trading/
```

## Command Line Interface

The framework includes a CLI for running backtests with configurable data providers and strategies.

### Basic Usage

```bash
# Run a backtest with default settings (MA crossover, Yahoo Finance, 1 year daily data)
python examples/cli.py

# Run with specific strategy and symbols
python examples/cli.py --strategy rsi --symbols AAPL MSFT --days 180

# Run with custom parameters
python examples/cli.py --strategy bb --bb-period 20 --bb-std 2.5 --initial-capital 50000

# Set the annualization period explicitly (defaults to a value derived from --interval)
python examples/cli.py --offline --interval 1wk --periods-per-year 52
```

### Data Providers

 ```bash
 # Use Yahoo Finance (default, requires network)
 python examples/cli.py --provider yfinance

 # Use Alpha Vantage (supports daily, weekly, monthly, intraday, and real-time)
 python examples/cli.py --provider alphavantage --interval 5m --days 30

 # Use Alpha Vantage with weekly data
 python examples/cli.py --provider alphavantage --interval weekly --days 365

 # Use Alpha Vantage with monthly adjusted data (includes dividends/splits)
 python examples/cli.py --provider alphavantage --interval monthly_adjusted --days 1095

 # Use Alpha Vantage with real-time quote
 python examples/cli.py --provider alphavantage --interval quote

 # Use Alpha Vantage with market status
 python examples/cli.py --provider alphavantage --interval market_status

 # Use Alpha Vantage with FX daily data
 python examples/cli.py --provider alphavantage --interval fx_daily --symbols USD/EUR GBP/USD

 # Use Alpha Vantage with FX intraday data
 python examples/cli.py --provider alphavantage --interval fx_5m --symbols USD/EUR

  # Use Alpha Vantage with crypto data
  python examples/cli.py --provider alphavantage --interval crypto_daily --symbols BTC ETH

  # Use Alpha Vantage with technical indicators (SMA is the default daily series)
  python examples/cli.py --provider alphavantage --interval sma --symbols AAPL MSFT
  python examples/cli.py --provider alphavantage --interval rsi --symbols AAPL
  python examples/cli.py --provider alphavantage --interval macd --symbols AAPL

  # Use Alpha Vantage sector performance
  python examples/cli.py --provider alphavantage --interval sector

  # Use Alpha Vantage with your own API key
  python examples/cli.py --provider alphavantage --alphavantage-key YOUR_API_KEY --interval 1h

 # Run offline with synthetic data (deterministic, no network required)
 python examples/cli.py --offline
 # or
 python examples/cli.py --provider synthetic
 ```

### Utility Commands

```bash
# List available strategies with their default parameters
python examples/cli.py --list-strategies

# List available data providers
python examples/cli.py --list-providers

# Generate a default config.yaml file
python examples/cli.py --init-config config.yaml

# Validate a config YAML file
python examples/cli.py --validate-config config.yaml
```

### Combined Mode

Run all strategies together and compare results:

```bash
python examples/cli.py --combined --symbols AAPL MSFT GOOGL --days 365
```

The analysis flags work in combined mode as well. Combined mode runs one
backtest per strategy, so there is no combined equity curve to analyse, and
the analysis is reported for the best strategy of the comparison:

```bash
python examples/cli.py --combined --offline --regime --symbols AAPL --days 120
```

The JSON output of a combined run carries the analysis under the same keys as
a single run, next to the `best_strategy` it belongs to.

### Configuration

Load settings from a YAML config file:

```bash
python examples/cli.py --config config.yaml
```

Every section of the file configures the run: the `data` section picks the
provider, the cache directory, the bar interval and the history span, the
`backtest` section the starting capital, the costs and the annualization
period, the `risk` section the risk limits, and the `portfolio` section the
limit on the number of open positions.

A flag that is given on the command line wins over the file, so
`--initial-capital 50000` overrides the `initial_capital` of the
configuration. The flags that have no value of their own (`--initial-capital`,
`--commission`, `--slippage` and `--risk-free-rate`) default to the value of
the configuration file, or to the built-in default when no file is given.
`--interval` works the same way: it overrides the `data.default_interval` of
the file, and defaults to the configured value, or to `"1d"` when no file is
given.

The `periods_per_year` of the configuration is replaced by the value that
matches the interval of the run, so the metrics are annualized for the data
that was fetched.

### Strategy Configuration

Instead of picking a built-in strategy with `--strategy` and overriding its
parameters one flag at a time, a strategy can be described in a YAML file and
passed with `--strategy-config`:

```yaml
type: rsi
name: MyRSI
parameters:
  period: 21
  oversold: 25
  overbought: 75
```

```bash
python examples/cli.py --offline --strategy-config strat.yaml --symbols AAPL --days 120
```

The `type` is resolved through the strategy registry (a primary key or an
alias), `name` is the label the run reports, and `parameters` is forwarded to
the strategy constructor. A `--strategy-config` file overrides `--strategy` and
every individual `--*-period` / `--*-multiplier` flag that would have set the
same parameter.

The reverse direction is available with `--output-strategy-config`, which writes
the configuration of the strategy that was run (the best result of an
optimization, the most recent walk-forward window, or the single strategy of a
regular backtest) to a YAML file, so it can be re-run later with
`--strategy-config`:

```bash
python examples/cli.py --offline --optimize --strategy ma \
    --ma-fast-range 5,15,5 --ma-slow-range 20,30,10 \
    --symbols AAPL --days 120 \
    --output-strategy-config best_ma.yaml
python examples/cli.py --offline --strategy-config best_ma.yaml --symbols AAPL --days 120
```

### Output

Save results to JSON or CSV:

```bash
python examples/cli.py --output results.json
python examples/cli.py --combined --output comparison.json
python examples/cli.py --output results.csv --output-format csv
```

### Error Reporting

A mistake in the invocation is reported as a one-line message and the exit
code `1`, not as a traceback:

```bash
$ python examples/cli.py --strategy nosuchstrategy --offline --symbols AAPL --days 30
Error: Unknown strategy: nosuchstrategy. Available: ['ema', 'ma', 'rsi', ...]

$ python examples/cli.py --config missing.yaml --offline --symbols AAPL --days 30
Error: could not read config file 'missing.yaml': No such file or directory

$ cat /tmp/cfg.yaml
backtest:
  initial_capital: abc
$ python examples/cli.py --config /tmp/cfg.yaml --offline --symbols AAPL --days 30
Error: invalid config field BacktestConfig.initial_capital: expected <class 'float'>, got str ('abc')
```

The same holds for a missing `--strategy-config` file, a `--output` path whose
directory does not exist and a configuration file that is not valid YAML.

A config file whose *values* have the wrong type (for example a string where a
number is expected, or an integer where a boolean is expected) is reported the
same way, instead of failing deep inside the library:

A `--strategy-config` file whose *content* is wrong is reported the same way,
instead of failing inside the strategy constructor:

```bash
$ python examples/cli.py --strategy-config broken.yaml --offline --symbols AAPL --days 30
Error: invalid strategy config 'broken.yaml': 'parameters' must be a mapping, got int
```

The `--*-range` arguments of the optimization mode are checked before the run
starts. A range is `min,max,step` and the step has to be greater than zero,
because a step of zero would make the grid search loop forever:

```bash
$ python examples/cli.py --optimize --ma-fast-range 5,20,0 --offline --symbols AAPL --days 30
Error: invalid --ma-fast-range: Invalid range 5,20,0: the step must be greater than 0
```

The `--mc-simulations` argument of the Monte Carlo mode is checked before the
run starts. It has to be at least 1, because a count of zero produces an empty
simulation set and a confusing downstream failure:

```bash
$ python examples/cli.py --monte-carlo --mc-simulations 0 --offline --symbols AAPL --days 30
Error: invalid --mc-simulations: the value must be at least 1 (got 0)
```

### Market Regime Analysis

Annotate a backtest's equity curve with market-regime labels
(bull/bear/sideways x low/high volatility):

```bash
# Run a backtest and print the regimes its equity curve traversed
python examples/cli.py --offline --regime --symbols AAPL --days 120

# Override the auto-derived volatility/return thresholds
python examples/cli.py --offline --regime --regime-window 30 --regime-vol-threshold 0.15 --regime-return-threshold 0.05

# Annualize the regime statistics with the frequency of the run
python examples/cli.py --offline --regime --interval 1wk --symbols AAPL --days 120
```

The regime volatility and the regime return are annualized with the same
`periods_per_year` as the rest of the run, and the block reports the value it
used.

### Trade Analysis

Detailed trade-level analysis including PnL statistics, holding periods, streaks, and per-symbol breakdowns:

```bash
# Run a backtest with detailed trade analysis
python examples/cli.py --offline --trade-analysis --symbols AAPL --days 120
```

### Alpha Vantage Specifics

 Alpha Vantage provider supports:
 - **Daily data**: `1d` / `daily` intervals via TIME_SERIES_DAILY_ADJUSTED
 - **Weekly data**: `1w`, `weekly`, `week` intervals via TIME_SERIES_WEEKLY
 - **Weekly adjusted data**: `1wa`, `weekly_adjusted` intervals via TIME_SERIES_WEEKLY_ADJUSTED (includes dividends/splits)
 - **Monthly data**: `1mo`, `monthly`, `month` intervals via TIME_SERIES_MONTHLY
 - **Monthly adjusted data**: `1ma`, `monthly_adjusted` intervals via TIME_SERIES_MONTHLY_ADJUSTED (includes dividends/splits)
 - **Intraday data**: `1m`, `5m`, `15m`, `30m`, `1h` / `60m` intervals via TIME_SERIES_INTRADAY
 - **Global Quote**: `quote`, `realtime`, `rt` intervals via GLOBAL_QUOTE (real-time single symbol quotes)
 - **Market Status**: `market_status`, `marketstatus` intervals via MARKET_STATUS (global market hours/status)
 - **FX Daily**: `fx_daily`, `fx`, `forex_daily` intervals via FX_DAILY (symbols as "FROM/TO", e.g., "USD/EUR")
 - **FX Intraday**: `fx_intraday`, `fx_1m`, `fx_5m`, `fx_15m`, `fx_30m`, `fx_60m` intervals via FX_INTRADAY
 - **Currency Exchange Rate**: real-time forex rates via CURRENCY_EXCHANGE_RATE (use `get_currency_exchange_rate()`)
- **Crypto Daily**: `crypto_daily`, `digital_daily` intervals via DIGITAL_CURRENCY_DAILY (symbols like "BTC", "ETH")
  - **Crypto Weekly**: `crypto_weekly`, `digital_weekly` intervals via DIGITAL_CURRENCY_WEEKLY
  - **Crypto Monthly**: `crypto_monthly`, `digital_monthly` intervals via DIGITAL_CURRENCY_MONTHLY
  - **Crypto Intraday**: `crypto_intraday`, `digital_intraday` intervals via DIGITAL_CURRENCY_INTRADAY
  - **Technical Indicators**: `sma`, `ema`, `rsi`, `macd`, `bbands`, `stoch`, etc. via TIME_SERIES_<INDICATOR> (default daily series resolution; use the interval as the indicator name)
  - **Sector Performance**: `sector`, `sector_performance`, `sectors` intervals via SECTOR (single global result across requested symbols)
  - **Commodities**: `wti`, `brent`, `natural_gas`, `copper`, `aluminum`, `corn`, `wheat`, `cotton`, `sugar`, `coffee`, `all_commodities` intervals via dedicated commodity endpoints (e.g., WTI, BRENT, COPPER)
  - **Precious Metals**: `gold`, `silver` intervals via GOLD_SILVER_SPOT (spot) and GOLD_SILVER_HISTORY (historical daily/weekly/monthly)
  - **Economic Indicators**: `gdp`, `real_gdp`, `gdp_per_capita`, `cpi`, `inflation`, `retail_sales`, `durables`, `unemployment`, `nonfarm_payroll`, `interest_rate`, `fed_funds_rate`, `treasury_yield`, `consumer_sentiment` intervals via dedicated economic endpoints
  - **Demo key**: Works out of the box with `"demo"` key (rate limited, warning logged)
  - **API key validation**: Optional warning when using demo key (configurable via `warn_on_demo`)

 For production use, get a free API key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key) and pass it via `--alphavantage-key` or config file.

### Example Scripts

See `examples/run_backtest.py` for a complete example of running backtests with multiple strategies.

For a deterministic, network-free demonstration, see
`examples/run_backtest_offline.py`. It runs the three built-in
strategies against seeded synthetic data and produces the same
output on every run:

```bash
python examples/run_backtest_offline.py
```

For a full analysis pass — market regime detection, Monte Carlo
simulation, and trade-level analysis — see
`examples/run_analysis.py`. It runs a single backtest against
synthetic data and prints all three analysis modules:

```bash
python examples/run_analysis.py
```

For a parameter optimization and walk-forward optimization demonstration, see
`examples/run_optimization.py`. It runs a grid search over the fast/slow MA
periods of the `MovingAverageCrossover` strategy against seeded synthetic
data, maximizing the Sharpe ratio, and then re-optimizes the same grid inside
sliding walk-forward windows to measure out-of-sample parameter stability:

```bash
python examples/run_optimization.py
```

For a trend-following demonstration using the Parabolic SAR indicator, see
`examples/run_parabolic_sar.py`. It runs the `ParabolicSARStrategy` against
seeded synthetic data, generating buy signals when price crosses above the
SAR (trend turns bullish) and sell signals when price crosses below the SAR
(trend turns bearish):

```bash
python examples/run_parabolic_sar.py
```

For a session-based VWAP demonstration, see `examples/run_vwap.py`. It runs
the `VWAPStrategy` against seeded synthetic data, generating buy signals
when price crosses above the VWAP and sell signals when price crosses below
the VWAP:

```bash
python examples/run_vwap.py
```

For an Ichimoku Cloud demonstration, see `examples/run_ichimoku.py`. It runs
the `IchimokuCloudStrategy` against seeded synthetic data, generating buy
signals when Tenkan-sen crosses above Kijun-sen with price above the cloud
and sell signals when Tenkan-sen crosses below Kijun-sen with price below
the cloud:

```bash
python examples/run_ichimoku.py
```

For a momentum trend-following demonstration using the MACD indicator, see
`examples/run_macd.py`. It runs the `MACDStrategy` against seeded synthetic
data, generating buy signals when the MACD line crosses above the signal line
(bullish crossover) and sell signals when the MACD line crosses below the
signal line (bearish crossover):

```bash
python examples/run_macd.py
```

For a Bollinger Bands mean-reversion demonstration, see
`examples/run_bollinger_bands.py`. It runs the `BollingerBandsStrategy` against
seeded synthetic data, generating buy signals when price touches the lower band
and sell signals when price touches the upper band:

```bash
python examples/run_bollinger_bands.py
```

For a momentum oscillator demonstration using the RSI indicator, see
`examples/run_rsi.py`. It runs the `RSIStrategy` against seeded synthetic
data, generating buy signals when RSI is oversold (< 30) and sell signals
when RSI is overbought (> 70):

```bash
python examples/run_rsi.py
```

For a trend-following demonstration using the Vortex Indicator, see
`examples/run_vortex.py`. It runs the `VortexStrategy` against seeded synthetic
data, generating buy signals when VI+ crosses above VI- and sell signals when
VI- crosses above VI+:

```bash
python examples/run_vortex.py
```

For an Ease of Movement demonstration, see `examples/run_ease_of_movement.py`.
It runs the `EaseOfMovementStrategy` against seeded synthetic data, generating
buy signals when EOM crosses above zero and sell signals when EOM crosses below
zero:

```bash
python examples/run_ease_of_movement.py
```

For a Percentage Price Oscillator demonstration, see `examples/run_ppo.py`. It
runs the `PercentagePriceOscillatorStrategy` against seeded synthetic data,
generating buy signals when PPO crosses above its signal line and sell signals
when PPO crosses below it:

```bash
python examples/run_ppo.py
```

For a Percentage Volume Oscillator demonstration, see `examples/run_pvo.py`.
It runs the `PercentageVolumeOscillatorStrategy` against seeded synthetic data,
generating buy signals when PVO crosses above its signal line and sell signals
when PVO crosses below it:

```bash
python examples/run_pvo.py
```

For a Stochastic Momentum Index demonstration, see `examples/run_smi.py`. It
runs the `StochasticMomentumIndexStrategy` against seeded synthetic data,
generating buy signals when the SMI line crosses above its signal line and sell
signals when it crosses below:

```bash
python examples/run_smi.py
```

For an Ultimate Oscillator demonstration, see `examples/run_ultimate_oscillator.py`.
It runs the `UltimateOscillatorStrategy` against seeded synthetic data,
generating buy signals when the oscillator crosses above its signal line and
sell signals when it crosses below:

```bash
python examples/run_ultimate_oscillator.py
```


## Data fetching

`DataProvider.fetch_many(requests)` fetches several distinct symbol/date
ranges in one call. Each request is a dict with optional `symbols`, `start`,
`end`, and `interval` keys (matching `fetch` defaults). It returns a dict
mapping a stable request key (`"symbols|start|end|interval"`) to a
`FetchResult`. `DataManager.fetch_many` wraps the same API and applies the
in-memory cache per request:

```python
from quant_trading.data.providers import DataManager

manager = DataManager([provider])
results = manager.fetch_many([
    {"symbols": ["AAPL"], "start": start1, "end": end1, "interval": "1d"},
    {"symbols": ["MSFT"], "start": start2, "end": end2, "interval": "1d"},
])
```

`DataManager.fetch_many` delegates to `DataProvider.fetch_many`, so providers can
batch requests. `YFinanceProvider` overrides `fetch_many` to group requests that
share a date range and fetch them with a single `yfinance.download(...,
group_by="ticker")` call rather than one HTTP request per symbol. Group results
are cached on disk (separate from per-symbol `fetch` cache keys) and each
request's result is keyed by its stable request key.

### DataManager

`DataManager` manages multiple data providers and provides in-memory caching:

```python
from quant_trading.data import (
    AlphaVantageProvider,
    DataManager,
    DataProvider,
    MarketData,
    SyntheticDataProvider,
    YFinanceProvider,
    create_synthetic_data,
    create_synthetic_provider,
)

# Create manager with providers
manager = DataManager([YFinanceProvider(), AlphaVantageProvider()])

# Fetch with specific provider
result = manager.fetch(["AAPL"], provider_name="alphavantage", interval="5m")

# Clear in-memory cache
manager.clear_cache()
```

### Alpha Vantage Provider

 The `AlphaVantageProvider` supports multiple endpoints:

 ```python
 from quant_trading.data.yfinance_provider import AlphaVantageProvider

 # Uses demo key by default (rate limited, logs warning)
 provider = AlphaVantageProvider()  # api_key defaults to "demo"

 # Or provide your own key
 provider = AlphaVantageProvider(api_key="YOUR_API_KEY")

 # Disable demo key warning
 provider = AlphaVantageProvider(api_key="demo", warn_on_demo=False)

 # Fetch daily data
 result = provider.fetch(["AAPL"], interval="1d")

 # Fetch weekly data
 result = provider.fetch(["AAPL"], interval="weekly")

 # Fetch weekly adjusted data (includes dividends/splits)
 result = provider.fetch(["AAPL"], interval="weekly_adjusted")

 # Fetch monthly data
 result = provider.fetch(["AAPL"], interval="monthly")

 # Fetch monthly adjusted data (includes dividends/splits)
 result = provider.fetch(["AAPL"], interval="monthly_adjusted")

 # Fetch intraday data (1m, 5m, 15m, 30m, 1h)
 result = provider.fetch(["AAPL"], interval="5m")

 # Fetch real-time single symbol quote
 result = provider.fetch(["AAPL"], interval="quote")

 # Fetch latest real-time quotes (batch)
 result = provider.fetch_latest(["AAPL", "MSFT"])

 # Get market status
 df = provider.get_market_status()

 # Get real-time currency exchange rate
 df = provider.get_currency_exchange_rate("USD", "EUR")

 # Fetch FX daily data (symbols as "FROM/TO")
 result = provider.fetch(["USD/EUR", "GBP/USD"], interval="fx_daily")

# Fetch FX intraday data
result = provider.fetch(["USD/EUR"], interval="fx_5m")

# Fetch crypto data
result = provider.fetch(["BTC", "ETH"], interval="crypto_daily")
result = provider.fetch(["BTC"], interval="crypto_weekly")
result = provider.fetch(["BTC"], interval="crypto_monthly")
result = provider.fetch(["BTC"], interval="crypto_intraday")

# Fetch technical indicators (indicator name as interval, default daily series)
result = provider.fetch(["AAPL"], interval="sma")
result = provider.fetch(["AAPL"], interval="rsi")

# Fetch sector performance
result = provider.fetch(["AAPL"], interval="sector")

# Fetch commodities (WTI, BRENT, Natural Gas, Copper, etc.)
result = provider.fetch(["WTI"], interval="wti")
result = provider.fetch(["BRENT"], interval="brent")
result = provider.fetch(["COPPER"], interval="copper")

# Fetch precious metals (gold/silver spot and history)
result = provider.fetch(["GOLD"], interval="gold")  # symbols "GOLD"/"XAU" or "SILVER"/"XAG"
result = provider.fetch(["SILVER"], interval="silver")
df = provider.get_gold_spot("GOLD")  # or "XAU" for gold, "SILVER"/"XAG" for silver
df = provider.get_gold_history("GOLD", interval="daily")  # also "weekly", "monthly"

# Fetch economic indicators (GDP, CPI, Unemployment, etc.)
result = provider.fetch(["GDP"], interval="gdp")
result = provider.fetch(["CPI"], interval="cpi")
df = provider.get_economic_indicator("REAL_GDP", interval="annual")
df = provider.get_economic_indicator("TREASURY_YIELD", interval="monthly", maturity="10year")

# Get a technical indicator directly as a DataFrame
df = provider.get_sma("AAPL")
df = provider.get_rsi("AAPL")
df = provider.get_technical_indicator("AAPL", indicator="SMA")

# Get commodity data directly
df = provider.get_commodity("WTI", interval="monthly")

# Get sector performance directly
df = provider.get_sector_performance()
  ```

Supported intervals:
  - Daily: `1d`, `daily`
  - Weekly: `1w`, `weekly`, `week`
  - Weekly Adjusted: `1wa`, `weekly_adjusted`
  - Monthly: `1mo`, `monthly`, `month`
  - Monthly Adjusted: `1ma`, `monthly_adjusted`
  - Intraday: `1m`, `5m`, `15m`, `30m`, `1h`, `60m`
  - Global Quote: `quote`, `realtime`, `rt`
  - Market Status: `market_status`, `marketstatus`
  - FX Daily: `fx_daily`, `fx`, `forex_daily` (symbols as "FROM/TO")
  - FX Intraday: `fx_intraday`, `fx_1m`, `fx_5m`, `fx_15m`, `fx_30m`, `fx_60m`
  - Crypto Daily: `crypto_daily`, `digital_daily`
  - Crypto Weekly: `crypto_weekly`, `digital_weekly`
  - Crypto Monthly: `crypto_monthly`, `digital_monthly`
  - Crypto Intraday: `crypto_intraday`, `digital_intraday`
  - Technical Indicators: `sma`, `ema`, `rsi`, `macd`, `bbands`, `stoch`, etc.
  - Sector Performance: `sector`, `sector_performance`, `sectors`
  - Commodities: `wti`, `brent`, `natural_gas`, `copper`, `aluminum`, `corn`, `wheat`, `cotton`, `sugar`, `coffee`, `all_commodities`
  - Precious Metals: `gold`, `silver` (spot via `get_gold_spot()`, history via `get_gold_history()`)
  - Economic Indicators: `gdp`, `real_gdp`, `gdp_per_capita`, `cpi`, `inflation`, `retail_sales`, `durables`, `unemployment`, `nonfarm_payroll`, `interest_rate`, `fed_funds_rate`, `treasury_yield`, `consumer_sentiment`
  - Real-time Batch: any other interval uses `BATCH_STOCK_PRICES`

  Additional methods:
  - `get_market_status()` - Returns DataFrame with global market hours/status
  - `get_currency_exchange_rate(from_currency, to_currency)` - Returns real-time FX rate
  - `get_technical_indicator(symbol, indicator="SMA", ...)` - Returns DataFrame for a TI (e.g. SMA, EMA, RSI, MACD, BBANDS, STOCH)
  - `get_sma(symbol)`, `get_ema(symbol)`, `get_rsi(symbol)`, `get_macd(symbol)`, `get_stoch(symbol)`, `get_bbands(symbol)` - Convenience wrappers for common indicators
  - `get_sector_performance()` - Returns DataFrame of sector performance rankings
  - `get_gold_spot(symbol)` - Returns spot price for gold ("GOLD"/"XAU") or silver ("SILVER"/"XAG")
  - `get_gold_history(symbol, interval)` - Returns historical prices for gold/silver (interval: "daily", "weekly", "monthly")
  - `get_commodity(function, interval)` - Returns commodity data (e.g. "WTI", "BRENT", "COPPER"; interval varies by commodity)
  - `get_economic_indicator(function, interval, **kwargs)` - Returns economic data (e.g. "REAL_GDP", "CPI", "UNEMPLOYMENT"; optional interval, maturity for treasury yields)
  - `search_symbols(query)` - Search for symbols by name or ticker

## Market Regime Analysis

A finished backtest can be inspected for the market regimes its equity curve
traversed. Regimes combine a direction signal (bull/bear/sideways) with a
volatility signal (low/high) derived from rolling-window statistics.

```python
from quant_trading.backtest import analyze_regimes

analysis = analyze_regimes(result, window=20)
print(analysis.current_regime)   # e.g. Regime.BULL_LOW_VOL
for seg in analysis.segments:
    print(seg.regime.value, seg.start, seg.end, seg.volatility, seg.return_pct)
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --regime --symbols AAPL --days 120
```

Optional explicit thresholds can be supplied to override the auto-derived
defaults:

```python
analysis = analyze_regimes(
    result,
    window=20,
    vol_threshold=0.15,
    return_threshold=0.05,
)
```

### Regime Annualization

The rolling volatility and the rolling mean return the detector compares
against the thresholds are annualized, so they have to be scaled with the
frequency of the data. `periods_per_year` is the number of periods that make
up a year (252 for daily bars, 52 for weekly, 12 for monthly):

```python
analysis = analyze_regimes(result, window=20, periods_per_year=52)
print(analysis.periods_per_year)   # 52
print(analysis.summary()["periods_per_year"])
```

The default is `252`, so a daily run behaves as before. The CLI derives the
value from the interval of the run in the same way it does for the backtest
metrics and the Monte Carlo simulation, so a weekly run reports a regime
volatility that is consistent with the rest of its output:

```bash
python examples/cli.py --offline --regime --periods-per-year 52 --symbols AAPL --days 120
```

A threshold that is left at its default is derived from the series itself (the
mean of the rolling statistics), and it is derived in the same annualized
units, so the labels of the segments do not change with the period count —
only the reported volatility does. A threshold that is given explicitly is a
fixed number in annualized units, so it does *not* follow the period count:
an explicit threshold has to be re-stated for the frequency it is used with.

## Monte Carlo Simulation

Run many simulated backtests by resampling the equity curve's daily
returns (bootstrap) or drawing from a fitted normal distribution
(parametric). This produces a distribution of outcomes — Sharpe, drawdown,
total return — and estimates the probability of profit and the confidence
interval around the original result.

```python
from quant_trading.monte_carlo import run_monte_carlo

mc = run_monte_carlo(result, n_simulations=1000, method="bootstrap", random_state=42)
print(f"Probability of profit: {mc.probability_of_profit():.2%}")
lower, upper = mc.get_confidence_interval("total_return_pct")
print(f"95% CI for total return: [{lower:.2f}%, {upper:.2f}%]")
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --monte-carlo --symbols AAPL --days 120
```

Override the simulation parameters:

```bash
python examples/cli.py --offline --monte-carlo --mc-simulations 500 --mc-method parametric --mc-confidence 0.99 --mc-seed 7
```

## Trade Analysis

Detailed trade-level analysis including PnL statistics, holding periods, consecutive win/loss streaks, monthly/weekly returns, and per-symbol breakdowns.

```python
from quant_trading.backtest import analyze_trades, print_trade_analysis

analysis = analyze_trades(result)
print_trade_analysis(analysis)
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --trade-analysis --symbols AAPL --days 120
```

This provides:
- **Overview**: Total trades, win rate, winning/losing trade counts
- **PnL Statistics**: Total/avg/median PnL, PnL of the positions that are still open, avg win/loss, largest win/loss, profit factor, expectancy
- **Holding Periods**: Average, median, min, max holding periods in days
- **Streaks**: Maximum consecutive wins/losses, current streak
- **Trade-Level Risk**: Annualized Sharpe and Sortino ratios of the per-trade return series, adjusted for the risk-free rate
- **Monthly/Weekly Returns**: Periodic return breakdowns
- **Per-Symbol Statistics**: Detailed breakdown by symbol

The trade-level Sharpe and Sortino are computed with the risk-free rate of the
run, so they are consistent with the Sharpe of the backtest itself. Pass the
rate explicitly to compute them with a different one:

```python
analysis = analyze_trades(result, risk_free_rate=0.05)
```

The CLI takes the rate from the run, so `--risk-free-rate` moves the backtest
Sharpe and the trade-level Sharpe together.

## Configuration

Create a `config.yaml` file:

```yaml
data:
  provider: "yfinance"
  cache_dir: "./data/cache"
  default_interval: "1d"
  default_period: "1y"

backtest:
  initial_capital: 100000.0
  commission: 0.001
  slippage: 0.0005
  risk_free_rate: 0.02
  periods_per_year: 252
  enable_stop_exits: false
  halt_on_portfolio_violation: false

risk:
  max_position_size: 0.1
  max_portfolio_risk: 0.02
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_drawdown: 0.20
  max_leverage: 1.0
  trailing_stop_pct: 0.0
  trailing_stop_activation_pct: 0.0

portfolio:
  rebalance_frequency: "monthly"
  max_positions: 20
  min_position_size: 0.01

logging_level: "INFO"
output_dir: "./output"
```

The `data` section configures the data layer of a run: the provider, the
cache directory, the bar interval and the history span. The `default_interval`
is the interval the run fetches with when no `--interval` flag is given, and
the `periods_per_year` follows the interval the data was actually fetched
with, so the metrics are annualized for the bars that were used.

Load in code:

```python
from quant_trading.config.settings import Config

config = Config.from_yaml("config.yaml")
```

A configuration that is handed to `run_backtest()` configures the run: the
`backtest` section provides the starting capital, the costs, the annualization
period and the engine switches, the `risk` section provides the limits of the
risk manager, and the `portfolio` section provides the limit on the number of
open positions.

```python
from quant_trading.backtest.engine import run_backtest
from quant_trading.config.settings import Config

config = Config.from_yaml("config.yaml")
result = run_backtest(
    strategy=strategy,
    symbols=["AAPL", "MSFT"],
    start=start,
    end=end,
    config=config,
)
```

The precedence is the same everywhere: a value that is passed explicitly wins
over the configured one, and the configured one wins over the built-in
default. `run_backtest(initial_capital=200000.0, config=config)` runs with
200000.0 even when the configuration asks for another amount, and a
configuration that says nothing about the starting capital runs with the
default of 100000.0. The configuration itself is never modified by a run.

A `DataConfig` only describes the data layer, so it leaves the backtest
settings, the risk limits and the position limit at their defaults.

## Risk Limits

`PortfolioLimit.check()` enforces the portfolio-level limits on every risk
check. Each breach is reported as a violation message, and
`RiskManager.check_portfolio()` turns those messages into a failed
`CheckResult`:

| Limit | Meaning | Default |
| --- | --- | --- |
| `max_positions` | Maximum number of open positions | `20` |
| `max_position_size` | Largest single position, as a fraction of the portfolio | `0.1` |
| `max_portfolio_risk` | Largest fraction of the portfolio value that may be at risk at once | `0.02` |
| `max_drawdown` | Drawdown from the peak that stops new positions | `0.20` |
| `max_leverage` | Largest gross exposure, as a multiple of the portfolio value | `1.0` |
| `stop_loss_pct` | Stop loss distance used to size the risk of each open position | `0.05` |

The risk of a position is the loss that would be realised if its planned stop
loss were hit: `size x entry price x stop_loss_pct`. The portfolio risk is the
sum of that risk over all open positions, expressed as a fraction of the
portfolio value. Measuring from the entry price keeps the risk committed to a
trade stable while the market moves.

Leverage is *gross* exposure: the absolute market value of every open position
divided by the portfolio value, so an equally sized long and short do not
cancel each other out.

`max_position_size` is measured on gross exposure as well, so a short position
is limited exactly like a long position of the same size. `PositionLimit`
applies the same rule to its `max_size` and `max_value` limits.

```python
from quant_trading.risk.limits import PortfolioLimit
from quant_trading.strategies.base import Position

limit = PortfolioLimit(max_portfolio_risk=0.02, max_leverage=1.0, max_position_size=1.0)
positions = {
    "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
}
limit.check(positions, portfolio_value=100000.0, peak_value=100000.0)
# ['Portfolio risk 3.00% exceeds max 2.00%']
```

The risk budget is a portfolio-wide commitment, so it also bounds the gross
exposure that may be open at once: with the default `max_portfolio_risk` of
`0.02` and a `stop_loss_pct` of `0.05`, more than 40% of the portfolio value
may be open before the risk limit is breached. The portfolio risk, leverage,
position-count and drawdown limits are reported when a portfolio is checked;
the signal gate below is what rejects an individual order that would breach
them.

`RiskManager.check_signal()` gates a signal before it is traded. The gate
measures the exposure the position would carry *after* the trade: a trade
brings a position to its target, so the position size is checked on the
target when the position is below it, and on the exposure the position
already carries when it is above it. The risk budget and the leverage limit
are increased by the increment alone — the target less the exposure the
symbol already carries — so a position that is already part of the way to its
target is not charged twice for the exposure it holds. A position that is
below its target can therefore be topped up by a later signal.

The gate also enforces `max_positions`: a `"buy"` or a `"short"` signal that
would open a **new** position is rejected when the portfolio already holds
`max_positions` positions. A signal that tops up a position that is already
open does not add a position and stays allowed, and a `"buy"` that covers an
open short reduces the gross exposure instead of adding a position, so both
stay allowed too. The number of positions is counted on the risk manager's
current position view, which is refreshed by `update_portfolio_value()` and
kept current by `sync_position()` as trades are executed.

The gate enforces the drawdown limit as well: a signal that adds exposure is
rejected while the portfolio is in a breach of `max_drawdown`, which is the
rule the rebalancer already applied to its buys. A `"buy"` that covers an open
short and a `"sell"` reduce the exposure, so they stay allowed while the
breach lasts, and the positions that are already open are still closed by
their own exit signals. A `max_drawdown` of `0.0` disables the limit. The
drawdown the gate reads is the one of the risk manager's current view, which
is refreshed by `update_portfolio_value()` at the end of every bar, so a
breach that happens on a bar is seen by the gate on the next bar.

A breach of the drawdown limit stops the run only when
`halt_on_portfolio_violation` is set. The default is `false`, so a run that
falls into a breach keeps trading on the positions it already holds and
reports the breach in `portfolio_violations`:

```yaml
backtest:
  halt_on_portfolio_violation: true
```

The stop loss, the take profit and the trailing stop of a position are advisory
by default: the risk manager computes the levels, but nothing closes the
position because of them. See [Stop Exits](#stop-exits) for the switch that
turns them into real exits.

## Short Selling

The backtest engine can open and close short positions. A strategy asks for
one with the `"short"` action; a `"buy"` signal against an open short buys it
back, so a short is closed the same way a long is.

| Action | Effect |
| --- | --- |
| `buy` | Opens or adds to a long position. Against an open short it covers that short instead. |
| `sell` | Reduces or closes a long position. It is rejected when no long position is held. |
| `short` | Opens or adds to a short position. It is rejected while a long position is held. |
| `hold` | No order. |

```python
from quant_trading.strategies.base import Signal

short = Signal(symbol="AAPL", action="short", price=150.0, strength=1.0)
cover = Signal(symbol="AAPL", action="buy", price=140.0, strength=1.0)
```

A short is sized exactly like a long: the signal strength times the
`max_position_size` limit, less the gross exposure the symbol already
carries. It is gated by the same limits as a buy — the position size, the
portfolio risk budget and the `max_leverage` limit — and all of them are
measured on *gross* exposure, so a long and a short of the same size do not
cancel each other out. The sale credits its proceeds to the cash balance, so
a short is not limited by the cash on hand.

The trade log records what each trade did to the position: `buy` and `sell`
act on a long, `short` opens a short and `cover` closes one. A short keeps
the raw execution price as its cost basis, so the entry fee it pays is booked
as realized PnL on the `short` trade and the `cover` books the price move and
the cover fee. A fully liquidated short round trip therefore reconciles the
same way a long one does:

```python
final_value - initial_capital == sum(trades["pnl"])
```

The stop loss and take profit helpers of the risk manager follow the
direction of the position. A long's stop sits below its entry price and its
target above it; a short's stop sits above the entry price and its target
below it, and the price is compared against each level in the direction that
triggers it.

```python
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Position

rm = RiskManager(stop_loss_pct=0.10, take_profit_pct=0.15)
rm.sync_position("AAPL", Position("AAPL", -100, 150.0, 150.0))
rm.get_position_stop_loss("AAPL")     # 165.0, above the entry price
rm.get_position_take_profit("AAPL")   # 127.5, below the entry price
rm.should_stop_loss("AAPL", 165.0)    # True
rm.should_take_profit("AAPL", 127.5)  # True
```

## Realized and Unrealized PnL

A run that ends with open positions has two kinds of PnL. The **realized** PnL
(`result.metrics.total_pnl`) is what the trade log booked: the PnL of the
completed round trips plus the entry fee of the shorts that are still open.
The **unrealized** PnL (`result.metrics.unrealized_pnl`) is the mark-to-market
PnL of the positions that are still open. The two halves explain the change of
the portfolio value:

```python
result.final_value - result.initial_capital == (
    result.metrics.total_pnl + result.metrics.unrealized_pnl
)
```

`result.unrealized_pnl` is the same figure, and it is `0.0` when the run ended
with every position closed. The CLI reports both halves next to the total
return, and the JSON output carries them as `total_pnl` and `unrealized_pnl`.
The same keys are present in every strategy entry of a **combined** run
(`--combined --output comparison.json`), so the identity can be read from
either output format.

The engine fills the unrealized PnL in because it is the only place that knows
the open positions. `calculate_backtest_metrics` sees an equity curve and a
trade log, and neither of them carries the market value of an open position,
so the field stays `0.0` when the function is called directly:

```python
from quant_trading.backtest.metrics import calculate_backtest_metrics

metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
metrics.unrealized_pnl  # 0.0 - the function cannot know the open positions
```

This is not the same figure as `analysis.open_position_pnl` of the
[trade analysis](#trade-analysis), which is the part of the realized PnL that
the positions that are still open booked.

## Trailing Stops

A trailing stop follows the price of a position once it has moved far enough in
its favour. It sits `trailing_stop_pct` away from the best price the position
has reached: below the highest price for a long, above the lowest price for a
short. The stop only ratchets in the favourable direction, so it never gives
back ground it has already locked in.

Trailing stops are disabled by default (`trailing_stop_pct: 0.0`).
`trailing_stop_activation_pct` is how far the position must move in its favour,
as a fraction of its entry price, before the stop starts to trail.

```python
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Position

rm = RiskManager(trailing_stop_pct=0.05)
rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
rm.update_trailing_stop("AAPL", 120.0)
rm.get_trailing_stop("AAPL")         # 114.0, 5% below the high of 120.0
rm.get_position_stop_loss("AAPL")    # 114.0, the trailing stop is the tighter one
```

The tighter of the two stops is always the one that is used: the higher level
for a long, the lower level for a short. A trailing stop that is still wider
than the fixed stop loss therefore leaves the fixed stop in place until the
price has moved far enough for the trailing stop to become the tighter one.

The risk manager is fed the prices it observes: `update_portfolio_value()` and
`sync_position()` both report the latest price of every position they know
about, so the trailing stop keeps following the market on their own. A caller
that tracks prices elsewhere can feed them in directly with
`update_trailing_stop(symbol, price)`.

## Stop Exits

The stop loss, the take profit and the trailing stop of a position are
computed by the risk manager, but they are advisory by default: the backtest
engine does not close a position because of them. `enable_stop_exits` turns
them into real exits.

```yaml
backtest:
  enable_stop_exits: true
```

With the exits on, every open position is measured against the levels the risk
manager computes for it after each bar, and the position is closed at that
bar's close when a level was reached:

- a long is closed when the close falls to (or below) its stop loss or rises
  to (or above) its take profit;
- a short is covered when the close rises to (or above) its stop loss or falls
  to (or below) its take profit.

The exit is an ordinary trade, so it is recorded in the trade log and the
accounting is unchanged: a run that is liquidated this way reconciles the same
way a run closed by a strategy signal does.

```python
final_value - initial_capital == sum(trades["pnl"])
```

The close is the price the engine knows on the bar, so no intrabar path is
assumed: a level that was crossed inside the bar is only acted on when the
close is on the other side of it. A trailing stop can therefore only be hit on
a bar *after* the one that ratcheted it, because the stop always sits below
the best price a long has reached (above it, for a short). The stop loss is
evaluated before the take profit, and a bar that reaches both closes the
position once, at that bar's close.

The exits are off by default, so a backtest that does not ask for them behaves
exactly as before. Note that a `stop_loss_pct` of `0.0` puts the stop of a
long at its entry price, so every close below the entry closes the position.

## Annualization Periods

The return, volatility, Sharpe, Sortino, Calmar and alpha figures are
annualized. `periods_per_year` controls how many periods make up a trading
year and defaults to `252` (daily bars). Use `52` for weekly bars or `12`
for monthly bars.

The same value is applied to every annualized metric, so the figures stay
mutually consistent:

```python
from quant_trading.backtest.metrics import calculate_backtest_metrics

metrics = calculate_backtest_metrics(equity_curve, periods_per_year=52)
```

It is configurable at every layer:

```python
# Configuration file / dataclass
config.backtest.periods_per_year = 52

# Backtest engine and convenience function
run_backtest(strategy, symbols, start, end, periods_per_year=52)
BacktestEngine(config=BacktestConfig(periods_per_year=52)).run(symbols, start, end)

# Optimizers and Monte Carlo simulation
GridSearch(..., periods_per_year=52)
WalkForwardOptimizer(..., periods_per_year=52)
run_monte_carlo(result, periods_per_year=52)

# Market regime analysis
analyze_regimes(result, periods_per_year=52)
regime_for_backtest(result, periods_per_year=52)
```

The CLI derives the value from `--interval` (252 for daily, 52 for weekly,
12 for monthly, and `252 * 390 / bar-minutes` for intraday intervals). Use
`--periods-per-year` to override it:

```bash
python examples/cli.py --offline --interval 1wk
python examples/cli.py --offline --interval 1wk --periods-per-year 52
```


For an Aroon demonstration using the Aroon indicator (Aroon Up and Aroon Down),
see `examples/run_aroon.py`. It runs the `AroonStrategy` against seeded
synthetic data, generating buy signals when Aroon Up crosses above Aroon Down
and sell signals when Aroon Down crosses above Aroon Up:

```bash
python examples/run_aroon.py
```

For a Keltner Channel demonstration using EMA and ATR volatility-based channels,
see `examples/run_keltner.py`. It runs the `KeltnerChannelStrategy` against
seeded synthetic data, generating buy signals when price breaks above the upper
channel and sell signals when price breaks below the lower channel:

```bash
python examples/run_keltner.py
```

For an Average True Range Channel Breakout demonstration using seeded synthetic data,
see `examples/run_atr.py`. It runs the `AverageTrueRangeStrategy`, which builds an ATR
channel anchored on the previous close and generates buy signals on upside breakouts
and sell signals on downside breakouts:

```bash
python examples/run_atr.py
```

For a Moving Average Crossover demonstration using fast/slow moving averages,
see `examples/run_ma_crossover.py`. It runs the `MovingAverageCrossover`
strategy against seeded synthetic data, generating buy signals on golden
crosses (fast MA crosses above slow MA) and sell signals on death crosses
(fast MA crosses below slow MA):

```bash
python examples/run_ma_crossover.py
```

For an Exponential Moving Average (EMA) Crossover demonstration using fast/slow EMAs,
see `examples/run_ema_crossover.py`. It runs the `EMACrossover` strategy against
seeded synthetic data, generating buy signals on bullish crosses (fast EMA crosses
above slow EMA) and sell signals on bearish crosses (fast EMA crosses below slow EMA):

```bash
python examples/run_ema_crossover.py
```

## License

MIT License

For a stochastic oscillator demonstration using the Stochastic indicator, see
`examples/run_stochastic.py`. It runs the `StochasticOscillatorStrategy`
against seeded synthetic data, generating buy signals when %K crosses above %D
in oversold territory (< 20) and sell signals when %K crosses below %D in
overbought territory (> 80):

```bash
python examples/run_stochastic.py
```

For a SuperTrend demonstration using the ATR-based SuperTrend indicator, see
`examples/run_super_trend.py`. It runs the `SuperTrendStrategy` against
seeded synthetic data, generating buy signals when price crosses above the
SuperTrend line (trend turns bullish) and sell signals when price crosses
below it (trend turns bearish):

```bash
python examples/run_super_trend.py
```

For a TRIX demonstration, see `examples/run_trix.py`.
```bash
python examples/run_trix.py
```
For a Donchian Channel demonstration using the highest high/lowest low over a
lookback period, see `examples/run_donchian.py`. It runs the
`DonchianChannelStrategy` against seeded synthetic data, generating buy signals
when price breaks above the upper band and sell signals when price breaks below
the lower band:

```bash
python examples/run_donchian.py
```

For a momentum demonstration using the Momentum indicator, see
`examples/run_momentum.py`. It runs the `MomentumStrategy` against seeded
synthetic data, generating buy signals when price momentum over the lookback
period is positive and above a threshold, and sell signals when momentum is
negative and below the negative threshold:

```bash
python examples/run_momentum.py
```
