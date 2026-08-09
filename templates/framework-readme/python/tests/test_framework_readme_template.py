import tempfile
import unittest
from pathlib import Path

from avishkar_template import instantiate

from framework_readme_template import FRAMEWORK_README_TEMPLATE


class TestFrameworkReadmeTemplate(unittest.TestCase):
    def test_has_every_standards_section_header(self):
        content = FRAMEWORK_README_TEMPLATE.files[0].spec.template
        for header in (
            "## Vision", "## Architecture", "## Folder Structure", "## Naming Standards",
            "## Interfaces", "## Extension Model", "## Examples", "## Best Practices",
            "## Anti-Patterns", "## Future Roadmap",
        ):
            self.assertIn(header, content)

    def test_instantiates_a_real_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            written = instantiate(FRAMEWORK_README_TEMPLATE, target, {"framework_name": "Example"})

            self.assertEqual(written, (target / "README.md",))
            text = (target / "README.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# Example Framework"))
            self.assertIn("## Vision", text)


if __name__ == "__main__":
    unittest.main()
