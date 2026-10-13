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

As of Phase 14, this shelf holds its first real, product-facing
template:
[`framework-readme/`](./framework-readme/README.md) — formalizes
STANDARDS.md §2.2's Framework template as a real, instantiable
`Template`, closing `template-factory`'s own README's Future Roadmap
item.

## Limitations
One standalone template (`framework-readme/`) committed as of Phase 14.

## Future improvements
- Additional formalized templates (e.g. the Chief Domain Agent tier)
  as real reuse need justifies the investment — see
  `framework-readme/README.md` Future Roadmap.
