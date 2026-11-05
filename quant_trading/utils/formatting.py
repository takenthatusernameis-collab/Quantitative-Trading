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


def format_shares(quantity: float, decimals: int = 0) -> str:
    """Format a share quantity with appropriate decimal places.

    Args:
        quantity: Number of shares/units.
        decimals: Number of decimal places for fractional shares.

    Returns:
        Formatted share quantity string.

    >>> format_shares(100)
    '100'
    >>> format_shares(10.5)
    '10.5'
    >>> format_shares(100, decimals=2)
    '100.00'

    """
    # Check if it's a whole number
    if abs(quantity - round(quantity)) < 1e-9:
        if decimals == 0:
            return f"{round(quantity):,}"
        else:
            return f"{round(quantity):,.{decimals}f}"
    else:
        # Has fractional part
        if decimals == 0:
            # Use reasonable precision for fractional shares
            return f"{quantity:g}"
        else:
            return f"{quantity:,.{decimals}f}"


def format_duration_days(days: float) -> str:
    """Format a duration in days as a human-readable string.

    Args:
        days: Number of days.

    Returns:
        Formatted duration string.

    >>> format_duration_days(1)
    '1 day'
    >>> format_duration_days(7)
    '1 week'
    >>> format_duration_days(30)
    '1 month'
    >>> format_duration_days(365)
    '1 year'
    >>> format_duration_days(3)
    '3 days'

    """
    if days < 0:
        return f"-{format_duration_days(abs(days))}"
    if days == 0:
        return "0 days"
    if days < 7:
        if days == 1:
            return "1 day"
        return f"{int(days) if days == int(days) else days} days"
    elif days < 30:
        weeks = days / 7
        if weeks == 1:
            return "1 week"
        if weeks == int(weeks):
            return f"{int(weeks)} weeks"
        return f"{weeks:.1f} weeks"
    elif days < 365:
        months = days / 30.44
        rounded_months = round(months)
        if rounded_months == 1:
            return "1 month"
        if abs(months - rounded_months) < 1e-9:
            return f"{rounded_months} months"
        return f"{months:.1f} months"
    else:
        years = days / 365.25
        rounded_years = round(years)
        if rounded_years == 1:
            return "1 year"
        if abs(years - rounded_years) < 1e-9:
            return f"{rounded_years} years"
        return f"{years:.1f} years"


__all__ = [
    'format_currency',
    'format_percent',
    'format_number',
    'format_basis_points',
    'format_shares',
    'format_duration_days',
]
