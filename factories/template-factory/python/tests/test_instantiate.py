import tempfile
import unittest
from pathlib import Path

from avishkar_prompt import PromptVariable, PromptVersion

from avishkar_template import Template, TemplateFile, TemplateInstantiationError, instantiate


class TestInstantiate(unittest.TestCase):
    def test_writes_files_and_creates_nested_directories(self):
        template = Template(
            name="demo",
            version="1.0.0",
            files=(
                TemplateFile(
                    relative_path="README.md",
                    spec=PromptVersion(
                        version="1.0.0", template="# {name}\n", variables=(PromptVariable(name="name"),)
                    ),
                ),
                TemplateFile(
                    relative_path="nested/config.txt",
                    spec=PromptVersion(version="1.0.0", template="static content"),
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            written = instantiate(template, target, {"name": "Demo Module"})

            self.assertEqual(len(written), 2)
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "# Demo Module\n")
            self.assertEqual((target / "nested" / "config.txt").read_text(encoding="utf-8"), "static content")

    def test_refuses_to_overwrite_by_default(self):
        template = Template(
            name="demo",
            version="1.0.0",
            files=(TemplateFile(relative_path="README.md", spec=PromptVersion(version="1.0.0", template="v1")),),
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "README.md").write_text("existing content", encoding="utf-8")

            with self.assertRaises(TemplateInstantiationError):
                instantiate(template, target, {})

            # untouched
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "existing content")

    def test_overwrite_true_replaces_existing_file(self):
        template = Template(
            name="demo",
            version="1.0.0",
            files=(TemplateFile(relative_path="README.md", spec=PromptVersion(version="1.0.0", template="v2")),),
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "README.md").write_text("v1", encoding="utf-8")

            instantiate(template, target, {}, overwrite=True)

            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "v2")

    def test_no_files_written_when_any_collision_exists(self):
        template = Template(
            name="demo",
            version="1.0.0",
            files=(
                TemplateFile(relative_path="a.txt", spec=PromptVersion(version="1.0.0", template="a")),
                TemplateFile(relative_path="b.txt", spec=PromptVersion(version="1.0.0", template="b")),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "b.txt").write_text("existing", encoding="utf-8")

            with self.assertRaises(TemplateInstantiationError):
                instantiate(template, target, {})

            self.assertFalse((target / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
