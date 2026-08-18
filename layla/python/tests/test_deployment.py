import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_memory.backends.file_backend import FileMemoryPolicy
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.deployment import (
    HealthServer,
    backup_data_directory,
    install_graceful_shutdown,
    restore_data_directory,
)
from avishkar_layla.runtime import ExecutiveRuntime


def _agent(name, domain, response_text):
    blueprint = AgentBlueprint(name=name, domain=domain, version="0.1.0", mission="test", default_model="mock-fast")
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)


def _runtime():
    orchestrator = Orchestrator([_agent("finance-agent", "Finance", "x")])
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return ExecutiveRuntime(orchestrator=orchestrator, agent_domains={"finance-agent": "Finance"}, memory=memory, sleep_fn=lambda s: None)


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class TestHealthServerLiveness(unittest.TestCase):
    def test_health_endpoint_reports_not_alive_before_any_run_forever_iteration(self):
        runtime = _runtime()
        server = HealthServer(runtime, port=0)
        server.start()
        try:
            status, body = _get(f"http://127.0.0.1:{server.port}/health")
            self.assertEqual(status, 503)
            self.assertFalse(body["alive"])
        finally:
            server.stop()

    def test_health_endpoint_reports_alive_after_a_real_run_forever_iteration(self):
        runtime = _runtime()
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)
        server = HealthServer(runtime, port=0)
        server.start()
        try:
            status, body = _get(f"http://127.0.0.1:{server.port}/health")
            self.assertEqual(status, 200)
            self.assertTrue(body["alive"])
        finally:
            server.stop()

    def test_unknown_path_returns_404(self):
        runtime = _runtime()
        server = HealthServer(runtime, port=0)
        server.start()
        try:
            status, body = _get(f"http://127.0.0.1:{server.port}/nonexistent")
            self.assertEqual(status, 404)
        finally:
            server.stop()


class TestHealthServerFullReport(unittest.TestCase):
    def test_report_endpoint_returns_the_real_production_health_report_as_json(self):
        runtime = _runtime()
        runtime.run_forever(max_iterations=1, tick_interval_seconds=0.0)
        server = HealthServer(runtime, port=0)
        server.start()
        try:
            status, body = _get(f"http://127.0.0.1:{server.port}/health/report")
            self.assertEqual(status, 200)
            self.assertIn("operational", body)
            self.assertIn("delegation_totals", body)
            self.assertTrue(body["operational"]["alive"])
        finally:
            server.stop()


class TestGracefulShutdown(unittest.TestCase):
    class _FakeSignalModule:
        """Injectable stand-in for the real `signal` module -- lets the
        test assert real registration behavior without mutating this
        process's actual signal table."""
        SIGINT = 2
        # deliberately no SIGTERM attribute, simulating a platform
        # where that name is unavailable.

        def __init__(self):
            self.registered = {}

        def signal(self, sig, handler):
            self.registered[sig] = handler

    def test_handler_calls_runtime_request_shutdown(self):
        runtime = _runtime()
        fake_signals = self._FakeSignalModule()
        handler = install_graceful_shutdown(runtime, _signal_module=fake_signals)

        self.assertFalse(runtime._shutdown_requested.is_set())
        handler(fake_signals.SIGINT, None)
        self.assertTrue(runtime._shutdown_requested.is_set())

    def test_only_signals_the_platform_actually_has_are_registered(self):
        runtime = _runtime()
        fake_signals = self._FakeSignalModule()
        install_graceful_shutdown(runtime, _signal_module=fake_signals)

        # SIGINT=2 exists on the fake module and must be registered;
        # SIGTERM does not exist on it and must be silently skipped
        # rather than raising.
        self.assertEqual(list(fake_signals.registered.keys()), [2])


class TestBackupRestore(unittest.TestCase):
    def test_backup_creates_a_real_timestamped_directory_with_copied_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            backups = Path(tmp) / "backups"
            memory = FileMemoryPolicy(root)
            memory.remember("long_term", "fact-1", "hello")

            destination = backup_data_directory(root, backups, clock=lambda: 1_700_000_000.0)

            self.assertTrue(destination.exists())
            self.assertEqual(destination.parent, backups)
            self.assertTrue((destination / "long_term.json").exists())
            self.assertIn("hello", (destination / "long_term.json").read_text(encoding="utf-8"))

    def test_restore_replaces_root_dir_contents_with_the_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            backups = Path(tmp) / "backups"
            memory = FileMemoryPolicy(root)
            memory.remember("long_term", "fact-1", "original")
            destination = backup_data_directory(root, backups, clock=lambda: 1_700_000_000.0)

            # simulate real data loss / corruption after the backup
            memory.forget("long_term", "fact-1")
            memory.remember("long_term", "fact-2", "corrupted-state")

            restore_data_directory(destination, root)

            restored = FileMemoryPolicy(root)
            self.assertEqual(restored.recall("long_term", "fact-1"), "original")
            self.assertIsNone(restored.recall("long_term", "fact-2"))

    def test_two_backups_a_second_apart_get_distinct_directory_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            backups = Path(tmp) / "backups"
            FileMemoryPolicy(root)

            first = backup_data_directory(root, backups, clock=lambda: 1_700_000_000.0)
            second = backup_data_directory(root, backups, clock=lambda: 1_700_000_001.0)

            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
