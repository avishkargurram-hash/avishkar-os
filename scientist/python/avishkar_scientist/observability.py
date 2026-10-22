"""Observability and structured logging for Scientist OS (P8).

Provides structured JSON log formatting for grep/jq compatibility
and task execution metrics recording.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
import time
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON documents."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "ts": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        # Capture custom extra fields passed to logger
        for k, v in record.__dict__.items():
            if k not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName"
            ):
                log_obj[k] = v
        return json.dumps(log_obj, default=str)


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configures root logging with either structured JSON or standard stream."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Remove existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s in %(name)s: %(message)s")
        )
    root.addHandler(handler)


logger = logging.getLogger("avishkar_scientist")


def log_task_metric(
    task_id: int,
    task_type: str,
    duration_s: float,
    status: str,
    mission_id: Optional[str] = None,
    error: Optional[str] = None,
    **extra: Any,
) -> None:
    """Emits a structured task execution metric log entry."""
    extra_data = {
        "metric": "task_execution",
        "task_id": task_id,
        "task_type": task_type,
        "duration_ms": round(duration_s * 1000.0, 2),
        "status": status,
        "mission_id": mission_id,
    }
    if error:
        extra_data["error"] = str(error)
    extra_data.update(extra)

    lvl = logging.ERROR if status == "FAILED" else logging.INFO
    logger.log(lvl, f"Task {task_id} ({task_type}) {status} in {duration_s:.3f}s", extra=extra_data)
