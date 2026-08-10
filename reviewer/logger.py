"""
JSON-structured logger for the LLM Code Reviewer.

Every log line is a single JSON object. Fields common to every line:
  - timestamp   ISO-8601 UTC
  - level       DEBUG / INFO / WARNING / ERROR
  - run_id      8-char UUID prefix scoping a single Action invocation
  - model       active model name (when known)
  - logger      the logger's dotted name

Usage:
    from reviewer.logger import get_logger

    log = get_logger(__name__)
    log.info("Reviewing file", extra={"file_path": "app/auth.py", "duration_ms": 412})
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_RUN_ID: str = "unknown"
_MODEL: str = "unknown"


def configure(run_id: str, model: str) -> None:
    """Call once at startup to inject the run-level context into every log line."""
    global _RUN_ID, _MODEL
    _RUN_ID = run_id
    _MODEL = model


class _JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        # Base fields always present
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "run_id": _RUN_ID,
            "model": _MODEL,
            "message": record.getMessage(),
        }

        # Merge any extra= fields passed by the caller
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that emits JSON to stdout.

    The first call configures the root handler; subsequent calls are fast.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated imports
    if not logging.root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)

    return logger
