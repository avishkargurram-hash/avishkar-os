# Starter Kit Factory

## Purpose
Produces end-to-end, clone-and-go starter kits for common product shapes
(e.g. "agentic SaaS backend," "chat product with memory") — the tooling
behind the ready-made kits landing in [`starters/`](../../starters/README.md).

## Responsibilities
- Compose existing platform building blocks (an agent, a workflow, a
  memory backend, a router config) into one coherent, working starting
  point for a product-shaped need — not a from-scratch template.
- Keep each starter kit minimal: the smallest set of pieces that actually
  demonstrates a working product shape, not every capability the platform
  has.
- Feed `project-factory`, which uses a starter kit as the base when
  scaffolding a brand-new product repository.

## Architecture
_(To be designed in Phase 4.)_ Expected shape: each kit is a directory
under `starters/<kit-name>/` referencing specific versions of agents,
workflows, and config from the rest of the platform, plus a README
walking through what it demonstrates and how to adapt it.

## Inputs
A target product shape and the specific platform components to compose.

## Outputs
A starter kit package in `starters/<kit-name>/`.

## Dependencies
Whatever platform pieces the kit composes (typically `agents/`,
`workflows/`, `router/`, `memory/`).

## Examples
_(none yet.)_

## Limitations
Not implemented yet. Zero starter kits exist as of the initial scaffold.

## Future improvements
- A "kit freshness" check: flag kits referencing platform components that
  have since changed incompatibly.
