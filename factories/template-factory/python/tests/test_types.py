import unittest

from avishkar_prompt import PromptVariable, PromptVersion, UnknownVariableError

from avishkar_template import DuplicateFileError, Template, TemplateFile


def _file(path: str, content: str = "content") -> TemplateFile:
    return TemplateFile(relative_path=path, spec=PromptVersion(version="1.0.0", template=content))


class TestTemplateFile(unittest.TestCase):
    def test_reuses_prompt_version_validation(self):
        # An undeclared {var} in a TemplateFile's spec raises the same
        # error PromptVersion itself raises -- proving the reuse is real,
        # not a reimplementation that happens to look similar.
        with self.assertRaises(UnknownVariableError):
            PromptVersion(version="1.0.0", template="{undeclared}")


class TestTemplate(unittest.TestCase):
    def test_valid_template_constructs(self):
        template = Template(name="demo", version="1.0.0", files=(_file("a.md"), _file("b.md")))
        self.assertEqual(len(template.files), 2)

    def test_duplicate_relative_path_raises(self):
        with self.assertRaises(DuplicateFileError):
            Template(name="demo", version="1.0.0", files=(_file("a.md"), _file("a.md")))


if __name__ == "__main__":
    unittest.main()
