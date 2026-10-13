import json
import tempfile
import unittest
from pathlib import Path

from avishkar_agent import AgentBlueprint, InvalidBlueprintError


def _valid_dict(**overrides):
    data = {
        "name": "software-ai-engineering",
        "domain": "Software & AI Engineering",
        "version": "0.1.0",
        "mission": "Ship correct, maintainable software.",
        "default_model": "claude-opus-5",
    }
    data.update(overrides)
    return data


class TestAgentBlueprintValidation(unittest.TestCase):
    def test_valid_blueprint_constructs(self):
        blueprint = AgentBlueprint(
            name="software-ai-engineering",
            domain="Software & AI Engineering",
            version="0.1.0",
            mission="Ship correct, maintainable software.",
            default_model="claude-opus-5",
        )
        self.assertEqual(blueprint.max_iterations, 5)

    def test_non_kebab_case_name_rejected(self):
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint(
                name="Software_Engineering",
                domain="Software",
                version="0.1.0",
                mission="x",
                default_model="claude-opus-5",
            )

    def test_non_semver_version_rejected(self):
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint(
                name="software-engineering",
                domain="Software",
                version="v1",
                mission="x",
                default_model="claude-opus-5",
            )

    def test_empty_mission_rejected(self):
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint(
                name="software-engineering",
                domain="Software",
                version="0.1.0",
                mission="   ",
                default_model="claude-opus-5",
            )

    def test_zero_max_iterations_rejected(self):
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint(
                name="software-engineering",
                domain="Software",
                version="0.1.0",
                mission="x",
                default_model="claude-opus-5",
                max_iterations=0,
            )


class TestAgentBlueprintFromDict(unittest.TestCase):
    def test_from_dict_builds_equivalent_blueprint(self):
        blueprint = AgentBlueprint.from_dict(_valid_dict())
        self.assertEqual(blueprint.name, "software-ai-engineering")
        self.assertEqual(blueprint.max_iterations, 5)

    def test_from_dict_missing_required_field_raises(self):
        data = _valid_dict()
        del data["mission"]
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint.from_dict(data)

    def test_from_dict_parses_tool_refs(self):
        data = _valid_dict(
            tools=[
                {"kind": "tool", "name": "run_tests"},
                {"kind": "mcp", "server": "github", "tool_name": "create_pr"},
            ]
        )
        blueprint = AgentBlueprint.from_dict(data)
        self.assertEqual(blueprint.tools[0].kind, "tool")
        self.assertEqual(blueprint.tools[0].name, "run_tests")
        self.assertEqual(blueprint.tools[1].kind, "mcp")
        self.assertEqual(blueprint.tools[1].server, "github")

    def test_from_dict_unknown_tool_kind_raises(self):
        data = _valid_dict(tools=[{"kind": "carrier_pigeon", "name": "x"}])
        with self.assertRaises(InvalidBlueprintError):
            AgentBlueprint.from_dict(data)

    def test_from_dict_memory_policy_backend(self):
        data = _valid_dict(memory_policy={"backend": "in_memory"})
        blueprint = AgentBlueprint.from_dict(data)
        self.assertEqual(blueprint.memory_policy.backend, "in_memory")


class TestAgentBlueprintFromFile(unittest.TestCase):
    def test_from_file_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blueprint.json"
            path.write_text(json.dumps(_valid_dict()), encoding="utf-8")

            blueprint = AgentBlueprint.from_file(path)

            self.assertEqual(blueprint.name, "software-ai-engineering")

    def test_from_file_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blueprint.json"
            path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(InvalidBlueprintError):
                AgentBlueprint.from_file(path)


if __name__ == "__main__":
    unittest.main()
