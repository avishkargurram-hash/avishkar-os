import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from avishkar_core import get_logger

# Every test uses a unique logger name -- Logger configuration (format,
# level, and *the output stream itself*) is captured once per name on
# first use (idempotency is part of the contract: CONTRACT.md SS2 says
# repeated get_logger() calls must not register duplicate handlers). That
# means get_logger() must be called for the FIRST time only after
# redirect_stdout(buffer) is active, or the handler binds to the real
# stdout instead of the test's buffer -- reusing a name across tests
# would also read stale configuration. Both are why every test below
# calls get_logger() *inside* the redirect_stdout block, with a fresh
# unique name.
_counter = 0


def _unique_name() -> str:
    global _counter
    _counter += 1
    return f"test.logger.{_counter}"


class TestLoggerTextFormat(unittest.TestCase):
    def test_text_output_contains_level_module_message(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger = get_logger(_unique_name())
            logger.info("hello world")
        output = buffer.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("hello world", output)


class TestLoggerJsonFormat(unittest.TestCase):
    def test_json_output_matches_log_record_shape(self):
        name = _unique_name()
        buffer = io.StringIO()
        with patch.dict(os.environ, {"AVISHKAR_LOG_FORMAT": "json"}, clear=False):
            with redirect_stdout(buffer):
                logger = get_logger(name)
                logger.info("structured message", user_id="u-1")
        record = json.loads(buffer.getvalue().strip())
        self.assertEqual(record["level"], "INFO")
        self.assertEqual(record["message"], "structured message")
        self.assertEqual(record["module"], f"avishkar.{name}")
        self.assertIn("timestamp", record)
        self.assertEqual(record["fields"], {"user_id": "u-1"})
        self.assertIsNone(record["correlation_id"])

    def test_error_with_exception_includes_exception_block(self):
        name = _unique_name()
        buffer = io.StringIO()
        with patch.dict(os.environ, {"AVISHKAR_LOG_FORMAT": "json"}, clear=False):
            with redirect_stdout(buffer):
                logger = get_logger(name)
                try:
                    raise ValueError("boom")
                except ValueError as exc:
                    logger.error("operation failed", exception=exc)
        record = json.loads(buffer.getvalue().strip())
        self.assertEqual(record["exception"]["type"], "ValueError")
        self.assertEqual(record["exception"]["message"], "boom")
        self.assertIn("Traceback", record["exception"]["stacktrace"])


class TestLoggerBind(unittest.TestCase):
    def test_bind_attaches_correlation_id_to_subsequent_records(self):
        name = _unique_name()
        buffer = io.StringIO()
        with patch.dict(os.environ, {"AVISHKAR_LOG_FORMAT": "json"}, clear=False):
            with redirect_stdout(buffer):
                logger = get_logger(name).bind(correlation_id="corr-123")
                logger.info("bound message")
        record = json.loads(buffer.getvalue().strip())
        self.assertEqual(record["correlation_id"], "corr-123")

    def test_bind_does_not_mutate_original_logger(self):
        name = _unique_name()
        buffer = io.StringIO()
        with patch.dict(os.environ, {"AVISHKAR_LOG_FORMAT": "json"}, clear=False):
            with redirect_stdout(buffer):
                base_logger = get_logger(name)
                bound_logger = base_logger.bind(correlation_id="corr-456")
                base_logger.info("unbound message")
        record = json.loads(buffer.getvalue().strip())
        self.assertIsNone(record["correlation_id"])
        self.assertIsNot(base_logger, bound_logger)


class TestLoggerLevelFiltering(unittest.TestCase):
    def test_debug_suppressed_below_configured_level(self):
        name = _unique_name()
        buffer = io.StringIO()
        with patch.dict(os.environ, {"AVISHKAR_LOG_LEVEL": "WARNING"}, clear=False):
            with redirect_stdout(buffer):
                logger = get_logger(name)
                logger.debug("should not appear")
                logger.info("should not appear either")
                logger.warning("should appear")
        output = buffer.getvalue()
        self.assertNotIn("should not appear", output)
        self.assertIn("should appear", output)


class TestGetLoggerIdempotency(unittest.TestCase):
    def test_same_name_returns_cached_logger(self):
        name = _unique_name()
        self.assertIs(get_logger(name), get_logger(name))


if __name__ == "__main__":
    unittest.main()
