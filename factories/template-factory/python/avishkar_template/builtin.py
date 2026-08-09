"""The one built-in Template this framework ships. See CONTRACT.md SS5.

Formalizes STANDARDS.md SS2.1's Module template -- the shape every
shelf-package README in this repo (memory/, knowledge/, workflows/,
templates/) already follows by hand -- as a real, instantiable
Template instead of leaving it as unenforced prose.
"""

from __future__ import annotations

from avishkar_prompt import PromptVariable, PromptVersion

from .types import Template, TemplateFile

_MODULE_README_CONTENT = """# {module_name}

## Purpose
Why this exists, in one paragraph.

## Responsibilities
What this module owns. Bullet list. If a responsibility isn't here, this
module doesn't own it -- say where it lives instead.

## Architecture
How it's built internally. Diagram (mermaid or ASCII) if it clarifies more
than it costs.

## Interfaces
The concrete API/contract other modules call -- function/class signatures
or endpoint shapes, not prose. If it has no public interface yet, say so.

## Dependencies
What it requires from the rest of the platform (ideally: only `core/`).

## Inputs
What it consumes -- types/schemas, not just names.

## Outputs
What it produces.

## Examples
At least one runnable/copy-pasteable example.

## Limitations
What it deliberately doesn't do yet, or won't do.

## Future Roadmap
Known next steps, not a wishlist.
"""

MODULE_README_TEMPLATE = Template(
    name="module-readme",
    version="1.0.0",
    files=(
        TemplateFile(
            relative_path="README.md",
            spec=PromptVersion(
                version="1.0.0",
                template=_MODULE_README_CONTENT,
                variables=(PromptVariable(name="module_name", description="e.g. 'memory/' or 'FileMemoryPolicy'"),),
            ),
        ),
    ),
)
