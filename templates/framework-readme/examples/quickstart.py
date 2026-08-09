"""Framework README template -- quickstart.

Instantiates the Framework README template (STANDARDS.md SS2.2) for a
hypothetical new framework. Run directly:

    python templates/framework-readme/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in ("core/python", "factories/prompt-factory/python", "factories/template-factory/python", "templates/framework-readme/python"):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_template import instantiate  # noqa: E402

from framework_readme_template import FRAMEWORK_README_TEMPLATE  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "new-framework"
        written = instantiate(FRAMEWORK_README_TEMPLATE, target, {"framework_name": "Notification"})

        print(f"Wrote {written[0]}")
        print("\nFirst three lines:")
        print("\n".join((target / "README.md").read_text(encoding="utf-8").splitlines()[:3]))


if __name__ == "__main__":
    main()
