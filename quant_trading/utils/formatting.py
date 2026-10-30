"""Formatting helpers for the trading system."""


def format_currency(value: float, currency: str = "$", decimals: int = 2) -> str:
    """Format a number as a currency string.

    Args:
        value: Numeric value to format.
        currency: Currency symbol to prepend.
        decimals: Number of decimal places.

    Returns:
        Formatted currency string.

    >>> format_currency(1234.5)
    '$1,234.50'
    >>> format_currency(-1000, decimals=0)
    '-$1,000'

    """
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}"
    return f"{sign}{currency}{formatted}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format a ratio (e.g. 0.05) as a percentage string.

    Args:
        value: Ratio value to format.
        decimals: Number of decimal places.

    Returns:
        Formatted percentage string.

    >>> format_percent(0.05)
    '5.00%'
    >>> format_percent(1.5, decimals=1)
    '150.0%'

    """
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a number with thousands separators.

    Args:
        value: Numeric value to format.
        decimals: Number of decimal places.

    Returns:
        Formatted number string.

    >>> format_number(1234567)
    '1,234,567'
    >>> format_number(1234.5678, decimals=2)
    '1,234.57'

    """
    return f"{value:,.{decimals}f}"


def format_basis_points(bps: float, decimals: int = 1) -> str:
    """Format basis points as a human-readable percentage string.

    One basis point equals 0.01%, so 100 basis points = 1.00%.

    Args:
        bps: Value in basis points.
        decimals: Number of decimal places for the percentage.

    Returns:
        Formatted percentage string representing basis points.

    >>> format_basis_points(100)
    '1.0%'
    >>> format_basis_points(25, decimals=2)
    '0.25%'
    >>> format_basis_points(150)
    '1.5%'

    """
    return f"{bps / 10000 * 100:.{decimals}f}%"
