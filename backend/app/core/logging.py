"""
app/core/logging.py — Structured JSON logging configuration.
"""
from __future__ import annotations

import logging
import sys

from app.config import settings


def configure_logging() -> None:
    """
    Set up structured logging. In production, use a JSON formatter
    (compatible with Loki). In development, use a human-readable format.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.is_development:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        datefmt = "%H:%M:%S"
        formatter = logging.Formatter(fmt, datefmt=datefmt)
    else:
        # Production: emit JSON lines (compatible with Grafana Loki)
        try:
            import json

            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    log_entry = {
                        "ts": self.formatTime(record),
                        "level": record.levelname,
                        "logger": record.name,
                        "msg": record.getMessage(),
                        "module": record.module,
                        "lineno": record.lineno,
                    }
                    if record.exc_info:
                        log_entry["exc"] = self.formatException(record.exc_info)
                    return json.dumps(log_entry)

            formatter = JsonFormatter()
        except ImportError:
            formatter = logging.Formatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Module-level logger for app internals
logger = logging.getLogger("notelm")
