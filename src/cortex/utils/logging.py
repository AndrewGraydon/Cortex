"""Centralized structlog configuration for Cortex services.

All Cortex processes (core, npu, audio, display) use this to set up
consistent structured logging.
"""

from __future__ import annotations

import logging

import structlog

from cortex.security.log_redactor import log_redactor


def configure_logging(log_level: str = "INFO", json: bool = False) -> None:
    """Configure structlog for a Cortex service process.

    Args:
        log_level: Python log level name (DEBUG, INFO, WARNING, ERROR).
        json: If True, output JSON lines; otherwise, colored console output.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        log_redactor,
    ]

    if json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so non-structlog loggers work
    logging.basicConfig(level=level, format="%(message)s")
