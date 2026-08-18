"""End-to-end integration: real EmbodimentController (structural risk/
approval gate, ADR-0027) + real executors (ADR-0030/ADR-0034/ADR-0035)
registered for EMBODIMENT_BROWSER / EMBODIMENT_COMPUTER_CONTROL /
EMBODIMENT_HOME_ASSISTANT / EMBODIMENT_MQTT. Proves the full chain
Directive D Parts III/VII/VIII require: risk classification ->
approval -> only then a real action -- and that a denied request
never reaches the real executor at all.
"""

import json
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from avishkar_agent import ApprovalGate
from avishkar_core import EventBus

from avishkar_layla.approval import ApprovalManager
from avishkar_layla.embodiment import (
    EMBODIMENT_BROWSER,
    EMBODIMENT_COMPUTER_CONTROL,
    EMBODIMENT_HOME_ASSISTANT,
    EMBODIMENT_MQTT,
    EmbodimentController,
)
from avishkar_layla.executors.browser_executor import BrowserExecutor
from avishkar_layla.executors.computer_control_executor import ComputerControlExecutor
from avishkar_layla.executors.home_assistant_executor import HomeAssistantExecutor
from avishkar_layla.executors.mqtt_executor import MQTTExecutor
from avishkar_layla.mqtt.client import MQTTBridge

# Plain top-level import -- see test_mqtt_bridge.py's comment on the
# same import for why this can't be a package-relative import.
from _minimal_mqtt_broker import MinimalMQTTBroker


class TestRealBrowserExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.browser = BrowserExecutor(headless=True)

    def tearDown(self):
        self.browser.close()

    def test_approved_navigate_actually_drives_a_real_browser(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "navigate", {"url": "data:text/html,<h1 id=t>real</h1>"}, task_id="t1",
        )

        self.assertEqual(result.status, "completed")
        self.assertIn("data:", result.output["url"])
        text = controller.request(EMBODIMENT_BROWSER, "get_text", {"selector": "#t"}, task_id="t1")
        self.assertEqual(text.output["text"], "real")

    def test_low_risk_browser_navigation_does_not_require_approval(self):
        """EMBODIMENT_BROWSER is NOT in embodiment.py's
        _DEFAULT_HIGH_RISK_CAPABILITIES -- plain navigation classifies
        LOW via the real text classifier and completes without ever
        consulting the (denying) gate. This is existing, deliberate
        ADR-0027 behavior, not a gap this test introduces.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "navigate", {"url": "data:text/html,<h1>ok to load</h1>"}, task_id="t1",
        )
        self.assertEqual(result.status, "completed")

    def test_denied_high_risk_browser_action_never_reaches_the_real_browser(self):
        """A genuinely dangerous-sounding browser action (matching
        classify_risk()'s real HIGH patterns) IS gated, and denial
        means the real executor is never touched at all.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "click", {"selector": "#submit", "action": "wire transfer payment"}, task_id="t1",
        )

        self.assertEqual(result.status, "denied")
        # Structural proof the real browser was never touched: no page
        # was ever created, so _page is still None.
        self.assertIsNone(self.browser._page)


class TestRealComputerControlExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="avishkar-layla-test-")
        self.executor = ComputerControlExecutor(workspace_root=self.workspace, allowed_shell_commands=("python",))

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_approved_shell_command_actually_runs(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        result = controller.request(
            EMBODIMENT_COMPUTER_CONTROL, "run_shell", {"command": "python -c \"print('ran for real')\""},
            task_id="t1",
        )

        self.assertEqual(result.status, "completed")
        self.assertIn("ran for real", result.output["stdout"])

    def test_denied_file_write_never_touches_the_real_filesystem(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        result = controller.request(
            EMBODIMENT_COMPUTER_CONTROL, "write_file", {"path": "should_not_exist.txt", "content": "x"},
            task_id="t1",
        )

        self.assertEqual(result.status, "denied")
        import os

        self.assertFalse(os.path.exists(os.path.join(self.workspace, "should_not_exist.txt")))

    def test_computer_control_is_always_high_risk_even_for_an_innocuous_looking_action(self):
        """embodiment.py's _DEFAULT_HIGH_RISK_CAPABILITIES forces
        EMBODIMENT_COMPUTER_CONTROL to RISK_HIGH regardless of text --
        even a request that reads as harmless still requires approval.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        from avishkar_layla.types import RISK_HIGH

        result = controller.request(EMBODIMENT_COMPUTER_CONTROL, "list_dir", {"path": "."}, task_id="t1")
        self.assertEqual(result.risk_level, RISK_HIGH)
        self.assertEqual(result.status, "denied")


class _HAHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer real-test-token":
            self._send(401, {"message": "Unauthorized"})
            return
        self._send(200, [{"entity_id": "light.kitchen", "state": "off"}])

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestRealHomeAssistantExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), _HAHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        import os

        os.environ["TEST_HA_INTEGRATION_TOKEN"] = "real-test-token"
        self.executor = HomeAssistantExecutor(
            base_url=f"http://127.0.0.1:{self.port}", token_env="TEST_HA_INTEGRATION_TOKEN",
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        import os

        os.environ.pop("TEST_HA_INTEGRATION_TOKEN", None)

    def test_approved_list_states_actually_reaches_the_real_server(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_HOME_ASSISTANT, self.executor)

        result = controller.request(EMBODIMENT_HOME_ASSISTANT, "list_states", {}, task_id="t1")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output[0]["entity_id"], "light.kitchen")

    def test_denied_call_service_never_reaches_the_real_server(self):
        """EMBODIMENT_HOME_ASSISTANT is in _DEFAULT_HIGH_RISK_CAPABILITIES
        -- every action requires approval, including one that reads as
        completely innocuous.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_HOME_ASSISTANT, self.executor)

        result = controller.request(
            EMBODIMENT_HOME_ASSISTANT, "call_service",
            {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.kitchen"}}, task_id="t1",
        )

        self.assertEqual(result.status, "denied")


class TestRealMQTTExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.broker = MinimalMQTTBroker()
        self.bus = EventBus()
        self.bridge = MQTTBridge(self.bus, allowed_publish_topics=("home/#",))
        self.bridge.connect("127.0.0.1", self.broker.port, client_id="embodiment-test")
        self.executor = MQTTExecutor(self.bridge)

    def tearDown(self):
        self.bridge.disconnect()
        self.broker.stop()

    def test_approved_publish_actually_reaches_the_real_broker(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_MQTT, self.executor)

        result = controller.request(
            EMBODIMENT_MQTT, "publish", {"topic": "home/kitchen/light", "payload": b"on"}, task_id="t1",
        )

        self.assertEqual(result.status, "completed")
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not self.broker.received_publishes:
            time.sleep(0.05)
        self.assertEqual(self.broker.received_publishes, [("home/kitchen/light", b"on")])

    def test_denied_publish_never_reaches_the_real_broker(self):
        """EMBODIMENT_MQTT is in _DEFAULT_HIGH_RISK_CAPABILITIES
        (ADR-0035) -- every action requires approval, including one
        that reads as completely innocuous.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_MQTT, self.executor)

        result = controller.request(
            EMBODIMENT_MQTT, "publish", {"topic": "home/kitchen/light", "payload": b"on"}, task_id="t1",
        )

        self.assertEqual(result.status, "denied")
        self.assertEqual(self.broker.received_publishes, [])


if __name__ == "__main__":
    unittest.main()
