from __future__ import annotations

import logging
import sys
from typing import Any
from trustdesk.core.config import settings


def configure_logging(level: str | None = None) -> None:
    """Configures structured standard logging for TrustDesk."""
    log_level_str = level or settings.log_level
    numeric_level = getattr(logging, log_level_str.upper(), logging.INFO)

    log_format = "%(asctime)s [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s"
    date_format = "%Y-%m-%dT%H:%M:%S%z"

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        stream=sys.stdout,
        force=True,
    )

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""
    return logging.getLogger(name)

