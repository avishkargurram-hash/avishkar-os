"""Real HomeAssistantExecutor tests. Runs a real, minimal, in-repo HTTP
server (stdlib `http.server`, its own thread) implementing Home
Assistant's actual REST API shape (`/api/states`,
`/api/services/<domain>/<service>`, `/api/config`, real Bearer-token
checking) -- the same "real local fixture" pattern
test_smtp_email_transport.py established. This is a genuine HTTP
conversation, not a mock of `requests`; only a live Home Assistant
installation is actually absent here (the documented ADAPTER READY
boundary).
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from avishkar_layla.executors.errors import UnknownActionError
from avishkar_layla.executors.home_assistant_executor import HomeAssistantExecutor, HomeAssistantNotConfiguredError

_VALID_TOKEN = "real-test-token"

_STATES = [
    {"entity_id": "light.living_room", "state": "off", "attributes": {"friendly_name": "Living Room Light"}},
    {"entity_id": "binary_sensor.front_door", "state": "off", "attributes": {"friendly_name": "Front Door"}},
]

_service_calls = []


class _HAHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A002 -- silence stdlib default stderr logging
        pass

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {_VALID_TOKEN}"

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 -- BaseHTTPRequestHandler's real method name
        if not self._authorized():
            self._send_json(401, {"message": "Unauthorized"})
            return
        if self.path == "/api/states":
            self._send_json(200, _STATES)
        elif self.path.startswith("/api/states/"):
            entity_id = self.path.rsplit("/", 1)[-1]
            match = next((s for s in _STATES if s["entity_id"] == entity_id), None)
            self._send_json(200, match) if match else self._send_json(404, {"message": "not found"})
        elif self.path == "/api/config":
            self._send_json(200, {"location_name": "Test Home", "version": "2024.1.0"})
        else:
            self._send_json(404, {"message": "not found"})

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            self._send_json(401, {"message": "Unauthorized"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/api/services/"):
            _, _, _, domain, service = self.path.split("/")
            _service_calls.append({"domain": domain, "service": service, "service_data": body})
            self._send_json(200, [{"entity_id": body.get("entity_id", "unknown"), "state": "on"}])
        else:
            self._send_json(404, {"message": "not found"})


class RealHomeAssistantServerTestCase(unittest.TestCase):
    def setUp(self):
        _service_calls.clear()
        self.server = HTTPServer(("127.0.0.1", 0), _HAHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


class TestHomeAssistantExecutorReal(RealHomeAssistantServerTestCase):
    def _executor(self):
        import os

        os.environ["TEST_HA_TOKEN"] = _VALID_TOKEN
        return HomeAssistantExecutor(base_url=f"http://127.0.0.1:{self.port}", token_env="TEST_HA_TOKEN")

    def tearDown(self):
        import os

        os.environ.pop("TEST_HA_TOKEN", None)
        super().tearDown()

    def test_list_states_returns_real_parsed_entities(self):
        executor = self._executor()
        result = executor("list_states", {})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["entity_id"], "light.living_room")

    def test_get_state_for_a_specific_entity(self):
        executor = self._executor()
        result = executor("get_state", {"entity_id": "binary_sensor.front_door"})
        self.assertEqual(result["state"], "off")

    def test_get_state_for_unknown_entity_raises(self):
        executor = self._executor()
        with self.assertRaises(ConnectionError):
            executor("get_state", {"entity_id": "light.does_not_exist"})

    def test_call_service_actually_reaches_the_real_server(self):
        executor = self._executor()
        result = executor("call_service", {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.living_room"}})

        self.assertEqual(result[0]["state"], "on")
        self.assertEqual(len(_service_calls), 1)
        self.assertEqual(_service_calls[0], {
            "domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.living_room"},
        })

    def test_get_config_returns_real_response(self):
        executor = self._executor()
        result = executor("get_config", {})
        self.assertEqual(result["location_name"], "Test Home")

    def test_invalid_token_is_rejected_with_a_real_401(self):
        import os

        os.environ["TEST_HA_TOKEN"] = "wrong-token"
        executor = HomeAssistantExecutor(base_url=f"http://127.0.0.1:{self.port}", token_env="TEST_HA_TOKEN")
        with self.assertRaises(HomeAssistantNotConfiguredError):
            executor("list_states", {})

    def test_unknown_action_raises(self):
        executor = self._executor()
        with self.assertRaises(UnknownActionError):
            executor("teleport", {})


class TestHomeAssistantExecutorMissingConfig(unittest.TestCase):
    def test_missing_base_url_raises_adapter_ready(self):
        import os

        os.environ.pop("TEST_HA_URL_MISSING", None)
        executor = HomeAssistantExecutor(base_url_env="TEST_HA_URL_MISSING", token_env="TEST_HA_TOKEN_MISSING")
        with self.assertRaises(HomeAssistantNotConfiguredError) as ctx:
            executor("list_states", {})
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_missing_token_raises_adapter_ready(self):
        import os

        os.environ.pop("TEST_HA_TOKEN_MISSING", None)
        executor = HomeAssistantExecutor(base_url="http://127.0.0.1:9", token_env="TEST_HA_TOKEN_MISSING")
        with self.assertRaises(HomeAssistantNotConfiguredError) as ctx:
            executor("list_states", {})
        self.assertIn("ADAPTER READY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
