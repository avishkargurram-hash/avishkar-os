"""Framework README template -- the first concrete, product-facing
Template committed under templates/ (Phase 14), rather than only the
Module template (MODULE_README_TEMPLATE) that ships inside
factories/template-factory itself.

Formalizes STANDARDS.md SS2.2's Framework template -- the shape every
`factories/*`, `core/`, and `router/` README already follows by hand
-- as a real, instantiable Template, closing the gap
template-factory's own README Future Roadmap named explicitly.
"""

from __future__ import annotations

from avishkar_prompt import PromptVariable, PromptVersion
from avishkar_template import Template, TemplateFile

_FRAMEWORK_README_CONTENT = """# {framework_name} Framework

## Vision
What this framework makes possible platform-wide, and why it must be a
framework (reusable, extensible) rather than a one-off implementation.

## Architecture
How it's built internally, including its major components and how they
fit together. Diagram if it clarifies more than it costs.

## Folder Structure
The layout inside this framework's own directory, and (if it produces a
shelf) the layout of what it produces.

## Naming Standards
Any naming conventions specific to this framework's artifacts, beyond the
platform-wide rules in STANDARDS.md SS3.

## Interfaces
The concrete API/contract this framework exposes to its consumers
(agents, products, other frameworks) -- signatures, not prose.

## Extension Model
How someone adds a new capability *through* this framework (a new agent
blueprint type, a new prompt category, a new graph pattern) without
modifying the framework's core.

## Examples
At least one runnable/copy-pasteable example of using this framework end
to end.

## Best Practices
What good usage of this framework looks like.

## Anti-Patterns
Specific, named misuses to avoid -- and what to do instead.

## Future Roadmap
Known next steps, not a wishlist.
"""

FRAMEWORK_README_TEMPLATE = Template(
    name="framework-readme",
    version="1.0.0",
    files=(
        TemplateFile(
            relative_path="README.md",
            spec=PromptVersion(
                version="1.0.0",
                template=_FRAMEWORK_README_CONTENT,
                variables=(PromptVariable(name="framework_name", description="e.g. 'Memory' or 'Evaluation'"),),
            ),
        ),
    ),
)
