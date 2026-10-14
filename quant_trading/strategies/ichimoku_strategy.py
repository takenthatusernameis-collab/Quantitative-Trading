
class IchimokuCloudStrategy(Strategy):
    """Ichimoku Cloud Strategy.

    The Ichimoku Cloud (Ichimoku Kinko Hyo) is a collection of technical indicators
    that show support and resistance levels, momentum, and trend direction.
    It consists of five lines:
    1. Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 for the last 9 periods
    2. Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 for the last 26 periods
    3. Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2, plotted 26 periods ahead
    4. Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 for the last 52 periods, plotted 26 periods ahead
    5. Chikou Span (Lagging Span): Close price plotted 26 periods behind

    Trading signals:
    - Buy when Tenkan-sen crosses above Kijun-sen and price is above the cloud
    - Sell when Tenkan-sen crosses below Kijun-sen and price is below the cloud
    """

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
        name: str = "Ichimoku_Cloud",
    ):
        super().__init__(
            name,
            {
                "tenkan_period": tenkan_period,
                "kijun_period": kijun_period,
                "senkou_b_period": senkou_b_period,
            },
        )
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters."""
        if self.tenkan_period <= 0:
            raise ValueError("tenkan_period must be positive")
        if self.kijun_period <= 0:
            raise ValueError("kijun_period must be positive")
        if self.senkou_b_period <= 0:
            raise ValueError("senkou_b_period must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            # We need enough data for the longest period and the forward shift
            min_required = max(self.senkou_b_period, self.kijun_period) + self.kijun_period
            if len(df) < min_required:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Calculate Tenkan-sen (Conversion Line)
            tenkan_high = high.rolling(window=self.tenkan_period).max()
            tenkan_low = low.rolling(window=self.tenkan_period).min()
            tenkan_sen = (tenkan_high + tenkan_low) / 2

            # Calculate Kijun-sen (Base Line)
            kijun_high = high.rolling(window=self.kijun_period).max()
            kijun_low = low.rolling(window=self.kijun_period).min()
            kijun_sen = (kijun_high + kijun_low) / 2

            # Calculate Senkou Span A (Leading Span A)
            senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(self.kijun_period)

            # Calculate Senkou Span B (Leading Span B)
            senkou_b_high = high.rolling(window=self.senkou_b_period).max()
            senkou_b_low = low.rolling(window=self.senkou_b_period).min()
            senkou_b = ((senkou_b_high + senkou_b_low) / 2).shift(self.kijun_period)

            current_price = close.iloc[-1]
            current_tenkan = tenkan_sen.iloc[-1]
            current_kijun = kijun_sen.iloc[-1]
            current_senkou_a = senkou_a.iloc[-1]
            current_senkou_b = senkou_b.iloc[-1]
            prev_tenkan = tenkan_sen.iloc[-2]
            prev_kijun = kijun_sen.iloc[-2]
            timestamp = df.index[-1]

            # Skip if any values are NaN
            if (
                pd.isna(current_tenkan)
                or pd.isna(current_kijun)
                or pd.isna(current_senkou_a)
                or pd.isna(current_senkou_b)
                or pd.isna(prev_tenkan)
                or pd.isna(prev_kijun)
            ):
                continue

            # Determine cloud boundaries (upper and lower)
            cloud_top = max(current_senkou_a, current_senkou_b)
            cloud_bottom = min(current_senkou_a, current_senkou_b)

            # Bullish signal: Tenkan crosses above Kijun AND price above cloud
            if prev_tenkan <= prev_kijun and current_tenkan > current_kijun and current_price > cloud_top:
                strength = min(1.0, (current_tenkan - current_kijun) / current_kijun * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "tenkan_sen": current_tenkan,
                            "kijun_sen": current_kijun,
                            "senkou_span_a": current_senkou_a,
                            "senkou_span_b": current_senkou_b,
                            "cloud_top": cloud_top,
                            "cloud_bottom": cloud_bottom,
                            "signal_type": "tenkan_kijun_bullish_crossover",
                        },
                    )
                )
            # Bearish signal: Tenkan crosses below Kijun AND price below cloud
            elif prev_tenkan >= prev_kijun and current_tenkan < current_kijun and current_price < cloud_bottom:
                strength = min(1.0, (current_kijun - current_tenkan) / current_kijun * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "tenkan_sen": current_tenkan,
                            "kijun_sen": current_kijun,
                            "senkou_span_a": current_senkou_a,
                            "senkou_span_b": current_senkou_b,
                            "cloud_top": cloud_top,
                            "cloud_bottom": cloud_bottom,
                            "signal_type": "tenkan_kijun_bearish_crossover",
                        },
                    )
                )

        return signals
