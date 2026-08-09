import json
import tempfile
import unittest
from pathlib import Path

from avishkar_agent import AgentBlueprint
from avishkar_prompt import PromptVariable, PromptVersion
from avishkar_template import Template, TemplateFile, TemplateInstantiationError

from avishkar_starter_kit import StarterKit, materialize


def _kit() -> StarterKit:
    return StarterKit(
        name="demo",
        version="1.0.0",
        description="demo kit",
        blueprint=AgentBlueprint(
            name="demo-agent", domain="Demo", version="0.1.0",
            mission="Answer demo questions.", default_model="mock-fast",
        ),
        project_template=Template(
            name="demo-project",
            version="1.0.0",
            files=(
                TemplateFile(
                    relative_path="README.md",
                    spec=PromptVersion(
                        version="1.0.0", template="# {name}\n", variables=(PromptVariable(name="name"),)
                    ),
                ),
            ),
        ),
        components=("agent",),
    )


class TestMaterialize(unittest.TestCase):
    def test_writes_project_files_and_blueprint_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            result = materialize(_kit(), target, {"name": "Demo Project"})

            self.assertEqual(len(result.written), 2)
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "# Demo Project\n")

            blueprint_data = json.loads((target / "agent" / "blueprint.json").read_text(encoding="utf-8"))
            self.assertEqual(blueprint_data["name"], "demo-agent")
            self.assertEqual(blueprint_data["mission"], "Answer demo questions.")

    def test_blueprint_json_round_trips_through_agent_blueprint_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            materialize(_kit(), target, {"name": "Demo Project"})

            reloaded = AgentBlueprint.from_file(target / "agent" / "blueprint.json")

            self.assertEqual(reloaded.name, "demo-agent")
            self.assertEqual(reloaded.default_model, "mock-fast")

    def test_refuses_to_overwrite_existing_blueprint_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            (target / "agent").mkdir(parents=True)
            (target / "agent" / "blueprint.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(TemplateInstantiationError):
                materialize(_kit(), target, {"name": "Demo Project"})

    def test_overwrite_true_replaces_existing_blueprint_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            (target / "agent").mkdir(parents=True)
            (target / "agent" / "blueprint.json").write_text("{}", encoding="utf-8")

            materialize(_kit(), target, {"name": "Demo Project"}, overwrite=True)

            blueprint_data = json.loads((target / "agent" / "blueprint.json").read_text(encoding="utf-8"))
            self.assertEqual(blueprint_data["name"], "demo-agent")


if __name__ == "__main__":
    unittest.main()
