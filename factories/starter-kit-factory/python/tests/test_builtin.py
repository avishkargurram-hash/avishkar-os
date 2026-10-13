import tempfile
import unittest
from pathlib import Path

from avishkar_starter_kit import AGENT_WITH_MEMORY_AND_KNOWLEDGE, materialize


class TestAgentWithMemoryAndKnowledgeKit(unittest.TestCase):
    def test_materializes_a_complete_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "my-product"
            result = materialize(
                AGENT_WITH_MEMORY_AND_KNOWLEDGE,
                target,
                {
                    "package_name": "my-product",
                    "description": "A demo product built on Avishkar OS.",
                    "components_list": ", ".join(AGENT_WITH_MEMORY_AND_KNOWLEDGE.components),
                },
            )

            written_names = {p.name for p in result.written}
            self.assertEqual(
                written_names, {"pyproject.toml", ".gitignore", "README.md", "main.py", "blueprint.json"}
            )

    def test_generated_main_py_is_syntactically_valid_python(self):
        # The generated main.py isn't just documentation text -- it must
        # actually compile, proving the template renders real, runnable
        # source code, not a broken f-string escaping mistake.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "my-product"
            materialize(
                AGENT_WITH_MEMORY_AND_KNOWLEDGE,
                target,
                {
                    "package_name": "my_product",
                    "description": "A demo product built on Avishkar OS.",
                    "components_list": "agent, memory, knowledge, workflow",
                },
            )

            source = (target / "main.py").read_text(encoding="utf-8")
            compile(source, "main.py", "exec")  # raises SyntaxError if invalid

    def test_components_documents_what_the_kit_demonstrates(self):
        self.assertEqual(
            AGENT_WITH_MEMORY_AND_KNOWLEDGE.components, ("agent", "memory", "knowledge", "workflow")
        )


if __name__ == "__main__":
    unittest.main()
