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
As of Phase 9, both owning factories' real engines live inside their
own packages rather than a `templates/` copy — the same precedent
`memory/`, `knowledge/`, and `workflows/` set: when a factory's own
package *is* the reusable engine, this directory stays the conceptual
home without a redundant physical duplicate.
- Prompts: [`factories/prompt-factory/python/avishkar_prompt/`](../factories/prompt-factory/python/avishkar_prompt/)
  (`PromptVersion`, `PromptRegistry`, `render`, scoring/comparison).
- Doc/project templates: [`factories/template-factory/python/avishkar_template/`](../factories/template-factory/python/avishkar_template/)
  (`Template`, `TemplateRegistry`, `instantiate`), including the real,
  working `MODULE_README_TEMPLATE` (formalizing STANDARDS.md §2.1).

A concrete, product-facing prompt or template (e.g. a specific agent's
registered `PromptVersion`s, or an instantiated project skeleton) would
land under `templates/prompts/<name>/` or `templates/project/<name>/`
once one exists.

## Limitations
No standalone templates committed directly under `templates/` yet — see
Examples for where the real, working engines live.

## Future improvements
- None planned beyond what's tracked in the owning factories' READMEs.
