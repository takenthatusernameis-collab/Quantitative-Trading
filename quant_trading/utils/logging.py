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
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger = setup_logger(name)
    return logger
"""