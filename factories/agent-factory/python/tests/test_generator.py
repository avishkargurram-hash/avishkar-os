import tempfile
import unittest
from pathlib import Path

from avishkar_agent import AgentBlueprint, scaffold_agent
from avishkar_agent.generator import _AGENT_TEMPLATE_SECTIONS


def _blueprint() -> AgentBlueprint:
    return AgentBlueprint(
        name="test-domain-agent",
        domain="Test Domain",
        version="0.1.0",
        mission="Do the test domain thing.",
        default_model="claude-opus-5",
    )


class TestScaffoldAgent(unittest.TestCase):
    def test_writes_exactly_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test-domain-agent"
            paths = scaffold_agent(_blueprint(), target)

            self.assertEqual(len(paths), 3)
            for path in paths:
                self.assertTrue(path.exists())
            written = set(p.name for p in target.iterdir())
            self.assertEqual(written, {"blueprint.json", "README.md", "test_domain_agent_agent.py"})

    def test_blueprint_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test-domain-agent"
            blueprint_path, _, _ = scaffold_agent(_blueprint(), target)

            reloaded = AgentBlueprint.from_file(blueprint_path)

            self.assertEqual(reloaded.name, "test-domain-agent")
            self.assertEqual(reloaded.mission, "Do the test domain thing.")

    def test_readme_contains_all_30_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test-domain-agent"
            _, readme_path, _ = scaffold_agent(_blueprint(), target)

            readme_text = readme_path.read_text(encoding="utf-8")

            self.assertEqual(len(_AGENT_TEMPLATE_SECTIONS), 30)
            for index, section in enumerate(_AGENT_TEMPLATE_SECTIONS, start=1):
                self.assertIn(f"## {index}. {section}", readme_text)

    def test_module_stub_names_build_function_after_blueprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test-domain-agent"
            _, _, module_path = scaffold_agent(_blueprint(), target)

            module_text = module_path.read_text(encoding="utf-8")

            self.assertIn("def build_test_domain_agent(", module_text)


if __name__ == "__main__":
    unittest.main()
