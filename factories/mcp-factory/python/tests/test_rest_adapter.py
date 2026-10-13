"""Tests for RESTAdapter -- uses the `transport` injection seam instead
of a live network call, mirroring test_mcp_adapter.py's session_provider
pattern.
"""

import json
import unittest

from avishkar_integration.adapters.rest_adapter import RESTAdapter
from avishkar_integration.errors import ProtocolInvocationError
from avishkar_integration.types import ToolContract, ToolExecutionRequest


def _contract(method="GET", url="https://api.example.com/weather", **config) -> ToolContract:
    return ToolContract(
        identity="get_weather",
        description="Get current weather",
        protocol="rest",
        input_schema={"type": "object"},
        protocol_config={"method": method, "url": url, **config},
    )


class TestRESTAdapterDeclaration(unittest.TestCase):
    def test_register_tool_and_discover(self):
        adapter = RESTAdapter()
        adapter.register_tool(_contract())

        self.assertEqual([t.identity for t in adapter.discover_tools()], ["get_weather"])

    def test_construction_with_initial_tools(self):
        adapter = RESTAdapter(tools=(_contract(),))
        self.assertEqual(len(adapter.discover_tools()), 1)


class TestRESTAdapterGet(unittest.TestCase):
    def test_get_encodes_query_params_and_parses_json_response(self):
        captured = {}

        def fake_transport(method, url, headers, body):
            captured.update(method=method, url=url, headers=headers, body=body)
            return 200, json.dumps({"temp_f": 72}).encode()

        adapter = RESTAdapter(transport=fake_transport)
        contract = _contract()

        result = adapter.invoke(contract, ToolExecutionRequest(input={"city": "Paris"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output, {"temp_f": 72})
        self.assertEqual(captured["method"], "GET")
        self.assertIn("city=Paris", captured["url"])
        self.assertIsNone(captured["body"])


class TestRESTAdapterPost(unittest.TestCase):
    def test_post_sends_json_body(self):
        captured = {}

        def fake_transport(method, url, headers, body):
            captured.update(method=method, url=url, headers=headers, body=body)
            return 201, json.dumps({"id": "pr-1"}).encode()

        adapter = RESTAdapter(transport=fake_transport)
        contract = _contract(method="POST", url="https://api.example.com/prs")

        result = adapter.invoke(contract, ToolExecutionRequest(input={"title": "Add caching"}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.output, {"id": "pr-1"})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(json.loads(captured["body"]), {"title": "Add caching"})
        self.assertEqual(captured["headers"]["Content-Type"], "application/json")


class TestRESTAdapterErrors(unittest.TestCase):
    def test_http_error_status_maps_to_error_result(self):
        def fake_transport(method, url, headers, body):
            return 404, json.dumps({"error": "not found"}).encode()

        adapter = RESTAdapter(transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={}))

        self.assertEqual(result.status, "error")
        self.assertIn("not found", result.error)

    def test_transport_exception_normalized_to_protocol_invocation_error(self):
        def fake_transport(method, url, headers, body):
            raise ConnectionError("dns lookup failed")

        adapter = RESTAdapter(transport=fake_transport)

        with self.assertRaises(ProtocolInvocationError):
            adapter.invoke(_contract(), ToolExecutionRequest(input={}))

    def test_non_json_response_falls_back_to_text(self):
        def fake_transport(method, url, headers, body):
            return 200, b"plain text response"

        adapter = RESTAdapter(transport=fake_transport)
        result = adapter.invoke(_contract(), ToolExecutionRequest(input={}))

        self.assertEqual(result.output, "plain text response")


if __name__ == "__main__":
    unittest.main()
