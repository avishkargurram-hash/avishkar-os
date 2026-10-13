import dataclasses
import unittest

from avishkar_integration import RetryPolicy, ToolContract


class TestToolContract(unittest.TestCase):
    def test_defaults(self):
        contract = ToolContract(identity="t", description="d", protocol="rest", input_schema={"type": "object"})
        self.assertEqual(contract.version, "1.0.0")
        self.assertEqual(contract.health_status, "unknown")
        self.assertEqual(contract.auth_requirement, "none")
        self.assertEqual(contract.retry_policy, RetryPolicy())

    def test_qualified_name(self):
        contract = ToolContract(identity="get_weather", description="d", protocol="mcp", input_schema={})
        self.assertEqual(contract.qualified_name, "mcp:get_weather")

    def test_is_frozen(self):
        contract = ToolContract(identity="t", description="d", protocol="rest", input_schema={})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contract.identity = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
