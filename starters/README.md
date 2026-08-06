# starters/

## Purpose
The library of ready-to-clone starter kits for common product shapes —
the output of
[`factories/starter-kit-factory`](../factories/starter-kit-factory/README.md).
Used by `project-factory` as the base when scaffolding a brand-new product
repository.

## Responsibilities
- One directory per kit (`starters/<kit-name>/`), composing specific
  agents, workflows, router config, and memory backends into a coherent,
  minimal working starting point.
- Document what each kit demonstrates and how to adapt it for a real
  product.

## What does NOT belong here
- Kit-generation/composition logic — that's `starter-kit-factory`.
- Full product repositories themselves — those are created by
  `project-factory` *from* a starter kit, as separate repos, not stored
  here.

## Inputs
Output from `starter-kit-factory` only.

## Outputs
Clone-and-go starting points consumed by `project-factory` or directly by
engineers starting a new product.

## Dependencies
`agents/`, `workflows/`, `router/`, `memory/` (whatever a given kit
composes).

## Examples
_(none yet.)_

## Limitations
Empty as of the initial scaffold (2026-08-06). No product has been
scaffolded from a starter kit yet.

## Future improvements
- None planned beyond what's tracked in `starter-kit-factory`'s README.
