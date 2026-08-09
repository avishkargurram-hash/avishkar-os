# templates/

## Purpose
The library of finished, reusable templates — prompt templates (from
[`factories/prompt-factory`](../factories/prompt-factory/README.md)) and
document/project templates (from
[`factories/template-factory`](../factories/template-factory/README.md)).

## Responsibilities
- `templates/prompts/<name>/` — versioned prompt templates with their eval
  suite reference.
- `templates/docs/` — canonical doc templates (module README, ADR, RFC).
- `templates/project/` — reusable project-scaffolding fragments consumed
  by `project-factory`/`starter-kit-factory`.

## What does NOT belong here
- Template *generation* logic — that's `prompt-factory` / `template-factory`.
- One-off templates used by a single product — those live in that
  product's repo.

## Inputs
Output from `prompt-factory` and `template-factory` only.

## Outputs
Instantiable templates for any product or factory to consume.

## Dependencies
`core/`.

## Examples
As of Phase 8, the real prompt engine (`PromptVersion`, `PromptRegistry`,
`render`, scoring/comparison) lives inside
[`factories/prompt-factory/python/avishkar_prompt/`](../factories/prompt-factory/python/avishkar_prompt/)
rather than a `templates/prompts/<name>/` copy — the same precedent
`memory/`, `knowledge/`, and `workflows/` set: when a factory's own
package *is* the reusable engine, this directory stays the conceptual
home without a redundant physical duplicate. A concrete, product-facing
prompt (e.g. a specific agent's registered `PromptVersion`s) would land
under `templates/prompts/<name>/` once one exists. `template-factory`
(Phase 9, not yet built) will populate `templates/docs/` and
`templates/project/` the same way.

## Limitations
No standalone templates committed directly under `templates/` yet — see
Examples for where the real, working prompt engine lives.
`template-factory` (doc/project templates) is not built yet — see
ROADMAP.md Phase 9.

## Future improvements
- None planned beyond what's tracked in the owning factories' READMEs.
