"""Template Framework -- quickstart.

Instantiates the built-in Module README template for a real new shelf
package (a hypothetical `avishkar_example` module), then registers and
instantiates a small custom two-file project template. Run directly:

    python factories/template-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "prompt-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "template-factory" / "python"))

from avishkar_prompt import PromptVariable, PromptVersion  # noqa: E402

from avishkar_template import (  # noqa: E402
    MODULE_README_TEMPLATE,
    Template,
    TemplateFile,
    TemplateRegistry,
    instantiate,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)

        print("1. Instantiating the built-in Module README template:")
        written = instantiate(MODULE_README_TEMPLATE, target / "new-module", {"module_name": "avishkar_example"})
        print(f"   wrote {written[0]}")
        print(f"   first line: {written[0].read_text(encoding='utf-8').splitlines()[0]!r}\n")

        print("2. Registering and instantiating a custom two-file project template:")
        registry = TemplateRegistry()
        registry.register(
            "python-package-skeleton",
            Template(
                name="python-package-skeleton",
                version="1.0.0",
                files=(
                    TemplateFile(
                        relative_path="pyproject.toml",
                        spec=PromptVersion(
                            version="1.0.0",
                            template='[project]\nname = "{package_name}"\nversion = "0.1.0"\n',
                            variables=(PromptVariable(name="package_name"),),
                        ),
                    ),
                    TemplateFile(
                        relative_path=".gitignore",
                        spec=PromptVersion(version="1.0.0", template="__pycache__/\n*.pyc\n"),
                    ),
                ),
            ),
        )
        skeleton = registry.get("python-package-skeleton")
        written2 = instantiate(skeleton, target / "new-package", {"package_name": "avishkar-example"})
        for path in written2:
            print(f"   wrote {path}")


if __name__ == "__main__":
    main()
