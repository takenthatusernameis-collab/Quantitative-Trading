"""Logging configuration utilities."""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "quant_trading",
    level: str = "INFO",
    log_file: str | None = None,
    fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
) -> logging.Logger:
    """Configure and return a logger with console (and optional file) output.

    Repeated calls for the same name return the existing logger without
    duplicating handlers.

    Args:
        name: Logger name.
        level: Logging level name.
        log_file: Optional path to a log file.
        fmt: Log message format string.

    Returns:
        Configured logger instance.

    >>> logger = setup_logger("quant_trading.doctest.logger")
    >>> logger.name
    'quant_trading.doctest.logger'
    >>> setup_logger("quant_trading.doctest.logger") is logger
    True

    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(fmt)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger(name: str = "quant_trading") -> logging.Logger:
    """Return a logger, creating a default one if none exists.

    Args:
        name: Logger name.

    Returns:
        Logger instance.

    >>> logger = get_logger("quant_trading.doctest.logger")
    >>> logger.name
    'quant_trading.doctest.logger'
    >>> get_logger("quant_trading.doctest.logger") is logger
    True

    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger = setup_logger(name)
    return logger


def clear_loggers(*names: str) -> None:
    """Remove all handlers from the specified loggers.

    This is primarily useful in tests to ensure a clean logging state
    between test cases.

    Args:
        *names: Logger names to clear. If none are provided, clears the
            root logger handlers.

    Examples:
        >>> import logging
        >>> logger = setup_logger("quant_trading.doctest.clear")
        >>> len(logger.handlers) >= 1
        True
        >>> clear_loggers("quant_trading.doctest.clear")
        >>> len(logging.getLogger("quant_trading.doctest.clear").handlers)
        0

    """
    if not names:
        names = ("",)
    for name in names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except (OSError, ValueError):
                pass
        logger.handlers.clear()


__all__ = [
    'setup_logger',
    'get_logger',
    'clear_loggers',
]
