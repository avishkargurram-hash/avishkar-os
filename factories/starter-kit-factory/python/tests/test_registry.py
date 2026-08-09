import unittest

from avishkar_agent import AgentBlueprint
from avishkar_prompt import PromptVersion
from avishkar_template import Template, TemplateFile

from avishkar_starter_kit import DuplicateVersionError, StarterKit, StarterKitRegistry, UnknownVersionError


def _kit(version: str) -> StarterKit:
    return StarterKit(
        name="demo",
        version=version,
        description="demo kit",
        blueprint=AgentBlueprint(
            name="demo-agent", domain="Demo", version="0.1.0",
            mission="demo", default_model="mock-fast",
        ),
        project_template=Template(
            name="demo-project", version=version,
            files=(TemplateFile(relative_path="README.md", spec=PromptVersion(version=version, template="hi")),),
        ),
    )


class TestStarterKitRegistry(unittest.TestCase):
    def test_register_and_get_latest(self):
        registry = StarterKitRegistry()
        registry.register("demo", _kit("1.0.0"))
        registry.register("demo", _kit("2.0.0"))
        self.assertEqual(registry.get("demo").version, "2.0.0")

    def test_get_specific_version(self):
        registry = StarterKitRegistry()
        registry.register("demo", _kit("1.0.0"))
        registry.register("demo", _kit("2.0.0"))
        self.assertEqual(registry.get("demo", version="1.0.0").version, "1.0.0")

    def test_duplicate_version_raises(self):
        registry = StarterKitRegistry()
        registry.register("demo", _kit("1.0.0"))
        with self.assertRaises(DuplicateVersionError):
            registry.register("demo", _kit("1.0.0"))

    def test_unknown_name_raises(self):
        registry = StarterKitRegistry()
        with self.assertRaises(UnknownVersionError):
            registry.get("does-not-exist")

    def test_versions_lists_all_in_order(self):
        registry = StarterKitRegistry()
        registry.register("demo", _kit("1.0.0"))
        registry.register("demo", _kit("2.0.0"))
        self.assertEqual(registry.versions("demo"), ("1.0.0", "2.0.0"))


if __name__ == "__main__":
    unittest.main()
