"""Formatting helpers for the trading system."""


def format_currency(value: float, currency: str = "$", decimals: int = 2) -> str:
    """Format a number as a currency string."""
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}"
    return f"{sign}{currency}{formatted}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format a ratio (e.g. 0.05) as a percentage string."""
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a number with thousands separators."""
    return f"{value:,.{decimals}f}"
