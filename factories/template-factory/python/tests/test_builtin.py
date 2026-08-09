import tempfile
import unittest
from pathlib import Path

from avishkar_template import MODULE_README_TEMPLATE, instantiate


class TestModuleReadmeTemplate(unittest.TestCase):
    def test_has_every_standards_section_header(self):
        content = MODULE_README_TEMPLATE.files[0].spec.template
        for header in (
            "## Purpose", "## Responsibilities", "## Architecture", "## Interfaces",
            "## Dependencies", "## Inputs", "## Outputs", "## Examples",
            "## Limitations", "## Future Roadmap",
        ):
            self.assertIn(header, content)

    def test_instantiates_a_real_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            written = instantiate(MODULE_README_TEMPLATE, target, {"module_name": "example-module/"})

            self.assertEqual(written, (target / "README.md",))
            text = (target / "README.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# example-module/"))
            self.assertIn("## Purpose", text)


if __name__ == "__main__":
    unittest.main()
