"""Starter Kit Framework -- quickstart.

Materializes the built-in "agent-with-memory-and-knowledge" starter kit
into a real temporary directory, then actually *runs* the generated
main.py as a subprocess -- proving the generated project isn't just
syntactically valid, it genuinely works end to end. Run directly:

    python factories/starter-kit-factory/examples/quickstart.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PACKAGES = [
    _ROOT / "core" / "python",
    _ROOT / "router" / "python",
    _ROOT / "factories" / "agent-factory" / "python",
    _ROOT / "factories" / "memory-factory" / "python",
    _ROOT / "factories" / "knowledge-factory" / "python",
    _ROOT / "factories" / "mcp-factory" / "python",
    _ROOT / "factories" / "workflow-factory" / "python",
    _ROOT / "factories" / "prompt-factory" / "python",
    _ROOT / "factories" / "template-factory" / "python",
    _ROOT / "factories" / "starter-kit-factory" / "python",
]
for path in _PACKAGES:
    sys.path.insert(0, str(path))

from avishkar_starter_kit import AGENT_WITH_MEMORY_AND_KNOWLEDGE, materialize  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "my-product"

        print("1. Materializing the 'agent-with-memory-and-knowledge' starter kit:")
        result = materialize(
            AGENT_WITH_MEMORY_AND_KNOWLEDGE,
            target,
            {
                "package_name": "my_product",
                "description": "A demo product built on Avishkar OS.",
                "components_list": ", ".join(AGENT_WITH_MEMORY_AND_KNOWLEDGE.components),
            },
        )
        for path in result.written:
            print(f"   wrote {path.relative_to(target)}")

        print("\n2. Actually running the generated main.py as a subprocess:")
        import os

        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in _PACKAGES)
        proc = subprocess.run(
            [sys.executable, str(target / "main.py")],
            capture_output=True, text=True, cwd=str(target), env=env,
        )
        print(f"   exit code: {proc.returncode}")
        print(f"   stdout: {proc.stdout.strip()}")
        if proc.returncode != 0:
            print(f"   stderr: {proc.stderr.strip()}")


if __name__ == "__main__":
    main()
