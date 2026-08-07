"""Logger -- structured logging with text/json output modes.

See CONTRACT.md SS2 for the full contract, and
schemas/log-record.schema.json for the JSON record shape emitted when
AVISHKAR_LOG_FORMAT=json.
"""

from __future__ import annotations

import datetime
import json
import logging as _stdlib_logging
import os
import sys
import traceback
from typing import Any, Dict, Optional


def _resolve_format() -> str:
    return os.environ.get("AVISHKAR_LOG_FORMAT", "text").lower()


def _resolve_level() -> str:
    return os.environ.get("AVISHKAR_LOG_LEVEL", "INFO").upper()


class _JsonFormatter(_stdlib_logging.Formatter):
    def format(self, record: _stdlib_logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload["fields"] = fields
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type else "Unknown",
                "message": str(exc_value) if exc_value else "",
                "stacktrace": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            }
        return json.dumps(payload, default=str)


class _TextFormatter(_stdlib_logging.Formatter):
    def format(self, record: _stdlib_logging.LogRecord) -> str:
        timestamp = datetime.datetime.fromtimestamp(
            record.created, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{timestamp} {record.levelname:<8} {record.name}: {record.getMessage()}"]
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            parts.append(f"[correlation_id={correlation_id}]")
        fields = getattr(record, "fields", None)
        if fields:
            parts.append(" ".join(f"{k}={v!r}" for k, v in fields.items()))
        text = " ".join(parts)
        if record.exc_info:
            text += "\n" + "".join(traceback.format_exception(*record.exc_info))
        return text


_configured_names: set = set()


def _configure(name: str) -> _stdlib_logging.Logger:
    stdlib_logger = _stdlib_logging.getLogger(f"avishkar.{name}")
    stdlib_logger.propagate = False
    if name not in _configured_names:
        handler = _stdlib_logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter() if _resolve_format() == "json" else _TextFormatter())
        stdlib_logger.handlers = [handler]
        stdlib_logger.setLevel(getattr(_stdlib_logging, _resolve_level(), _stdlib_logging.INFO))
        _configured_names.add(name)
    return stdlib_logger


class Logger:
    """A structured logger bound to a module name and, optionally, extra
    fields attached to every record it emits (see bind()).
    """

    def __init__(self, name: str, extra_fields: Optional[dict] = None) -> None:
        self._name = name
        self._extra_fields = dict(extra_fields or {})
        self._stdlib_logger = _configure(name)

    def bind(self, **fields: Any) -> "Logger":
        """Return a new Logger that attaches `fields` to every subsequent
        record, without mutating this logger.
        """
        merged = {**self._extra_fields, **fields}
        return Logger(self._name, merged)

    def _log(
        self,
        level: int,
        message: str,
        exception: Optional[BaseException],
        fields: dict,
    ) -> None:
        merged_fields = {**self._extra_fields, **fields}
        correlation_id = merged_fields.pop("correlation_id", None)
        extra = {"correlation_id": correlation_id, "fields": merged_fields}
        exc_info = (type(exception), exception, exception.__traceback__) if exception else None
        self._stdlib_logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, message: str, **fields: Any) -> None:
        self._log(_stdlib_logging.DEBUG, message, None, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log(_stdlib_logging.INFO, message, None, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log(_stdlib_logging.WARNING, message, None, fields)

    def error(self, message: str, exception: Optional[BaseException] = None, **fields: Any) -> None:
        self._log(_stdlib_logging.ERROR, message, exception, fields)

    def critical(self, message: str, exception: Optional[BaseException] = None, **fields: Any) -> None:
        self._log(_stdlib_logging.CRITICAL, message, exception, fields)


_loggers: Dict[str, Logger] = {}


def get_logger(name: str) -> Logger:
    """Idempotent: repeated calls with the same name return loggers that
    share configuration (level, format) -- see CONTRACT.md SS2.
    """
    if name not in _loggers:
        _loggers[name] = Logger(name)
    return _loggers[name]
