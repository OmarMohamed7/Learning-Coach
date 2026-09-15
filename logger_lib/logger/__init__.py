from __future__ import annotations

import logging
import os

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def configure_logging(level: str | None = None) -> None:
    """Set up the root logger once. Level defaults to the LOG_LEVEL env var."""
    global _configured
    if _configured:
        return

    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=resolved_level, format=_FORMAT)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, configuring the shared setup on first use."""
    configure_logging()
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]
