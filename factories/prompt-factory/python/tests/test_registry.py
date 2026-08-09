import unittest

from avishkar_prompt import (
    DuplicateVersionError,
    PromptRegistry,
    PromptVariable,
    PromptVersion,
    UnknownVersionError,
)


def _version(v: str, template: str = "Hello {name}") -> PromptVersion:
    return PromptVersion(version=v, template=template, variables=(PromptVariable(name="name"),))


class TestPromptRegistry(unittest.TestCase):
    def test_register_and_get_latest(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        registry.register("greeting", _version("1.1.0"))

        latest = registry.get("greeting")

        self.assertEqual(latest.version, "1.1.0")

    def test_get_specific_version(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        registry.register("greeting", _version("1.1.0"))

        first = registry.get("greeting", version="1.0.0")

        self.assertEqual(first.version, "1.0.0")

    def test_duplicate_version_raises(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        with self.assertRaises(DuplicateVersionError):
            registry.register("greeting", _version("1.0.0"))

    def test_unknown_prompt_name_raises(self):
        registry = PromptRegistry()
        with self.assertRaises(UnknownVersionError):
            registry.get("does-not-exist")

    def test_unknown_version_raises(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        with self.assertRaises(UnknownVersionError):
            registry.get("greeting", version="9.9.9")

    def test_versions_lists_all_registered_versions_in_order(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        registry.register("greeting", _version("2.0.0"))
        self.assertEqual(registry.versions("greeting"), ("1.0.0", "2.0.0"))

    def test_render_through_registry(self):
        registry = PromptRegistry()
        registry.register("greeting", _version("1.0.0"))
        self.assertEqual(registry.render("greeting", {"name": "Ada"}), "Hello Ada")


if __name__ == "__main__":
    unittest.main()
