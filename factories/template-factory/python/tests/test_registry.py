import unittest

from avishkar_prompt import PromptVersion

from avishkar_template import DuplicateVersionError, Template, TemplateFile, TemplateRegistry, UnknownVersionError


def _template(version: str) -> Template:
    return Template(
        name="demo",
        version=version,
        files=(TemplateFile(relative_path="README.md", spec=PromptVersion(version=version, template="hi")),),
    )


class TestTemplateRegistry(unittest.TestCase):
    def test_register_and_get_latest(self):
        registry = TemplateRegistry()
        registry.register("demo", _template("1.0.0"))
        registry.register("demo", _template("2.0.0"))

        self.assertEqual(registry.get("demo").version, "2.0.0")

    def test_get_specific_version(self):
        registry = TemplateRegistry()
        registry.register("demo", _template("1.0.0"))
        registry.register("demo", _template("2.0.0"))

        self.assertEqual(registry.get("demo", version="1.0.0").version, "1.0.0")

    def test_duplicate_version_raises(self):
        registry = TemplateRegistry()
        registry.register("demo", _template("1.0.0"))
        with self.assertRaises(DuplicateVersionError):
            registry.register("demo", _template("1.0.0"))

    def test_unknown_name_raises(self):
        registry = TemplateRegistry()
        with self.assertRaises(UnknownVersionError):
            registry.get("does-not-exist")

    def test_unknown_version_raises(self):
        registry = TemplateRegistry()
        registry.register("demo", _template("1.0.0"))
        with self.assertRaises(UnknownVersionError):
            registry.get("demo", version="9.9.9")

    def test_versions_lists_all_in_order(self):
        registry = TemplateRegistry()
        registry.register("demo", _template("1.0.0"))
        registry.register("demo", _template("2.0.0"))
        self.assertEqual(registry.versions("demo"), ("1.0.0", "2.0.0"))


if __name__ == "__main__":
    unittest.main()
