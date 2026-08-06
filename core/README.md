# core/ — Core Engine

## Purpose
The minimal runtime substrate every other module in Avishkar OS depends
on: config, logging, the event bus, and module lifecycle/loading. This is
the one module with a hard, enforced dependency rule — see
[ARCHITECTURE.md](../ARCHITECTURE.md) §5.

## Responsibilities
- Configuration loading (env, per-module config) with a single consistent
  convention every factory and product uses.
- Structured logging with consistent format/levels across the whole
  platform (so logs from an agent, a workflow, and an MCP server are
  correlatable).
- An event bus for cross-module communication that doesn't require direct
  imports between unrelated modules.
- Module lifecycle: how a factory-generated module (agent, MCP server,
  graph) registers itself and gets discovered/loaded by a product.

## What does NOT belong here
- Anything domain-specific: no agent logic, no routing policy, no memory
  schema. If it's specific to what a module *does* rather than how modules
  *run*, it belongs in that module, not `core/`.
- **`core/` depends on nothing else inside this repository.** Every other
  module may depend on `core/`; the reverse is a bug, not a style
  preference — see ARCHITECTURE.md §5.

## Architecture
_(To be designed in Phase 1 — see [ROADMAP.md](../ROADMAP.md), the first
implementation priority because every other factory's output depends on
it.)_

## Inputs
Environment/config sources; module registration calls from other parts of
the platform.

## Outputs
Config values, log streams, event bus pub/sub, and the module registry
other code queries to discover what's loaded.

## Dependencies
None (by design — see above).

## Examples
_(none yet.)_

## Limitations
Not implemented yet. This is Phase 1's first deliverable — nothing else in
this platform can be considered "real" until `core/` exists, since every
other module's README declares a dependency on it.

## Future improvements
- Plugin/module hot-reload for local development once there's enough
  implemented to make that valuable.
