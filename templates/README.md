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
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06).

## Future improvements
- None planned beyond what's tracked in the owning factories' READMEs.
