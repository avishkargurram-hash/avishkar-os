# docs/

## Purpose
Home for documentation that doesn't fit inside a single module's README —
cross-cutting guides, onboarding material, and design explorations that
are too long-lived or too broad to live next to one factory or shelf.

## Responsibilities
- Onboarding: how a new engineer (or agent) gets productive in this repo
  beyond what CLAUDE.md/ARCHITECTURE.md/STANDARDS.md already cover.
- Cross-cutting guides that span multiple modules (e.g. "how a request
  flows from a product through the router, an agent, and back").
- Design explorations / spikes that informed a DECISIONS.md ADR, kept for
  reference once the ADR is written.

## Responsibilities it does NOT have
- Module-specific documentation — that belongs in the module's own
  README (see STANDARDS.md §2). Don't let `docs/` become a dumping ground
  that duplicates what a module README should say.
- Architecture decisions — those are ADRs in [DECISIONS.md](../DECISIONS.md),
  not files here.

## Inputs
Written directly by engineers/agents when a doc doesn't have a natural
module home.

## Outputs
Rendered documentation (currently plain Markdown; a static-site generator
may be added later if the volume justifies it — see Future improvements).

## Dependencies
None.

## Examples
[`final-integration.md`](./final-integration.md) (Phase 15) — a
cross-cutting guide showing how Core Engine, AI Router, Universal
Integration, Agent Framework, Memory, Knowledge, Workflow, Evaluation,
and Security connect, backed by a real, runnable script
([`final-integration-verify.py`](./final-integration-verify.py)) and
its actual captured output — exactly the "how a request flows through
the router, an agent, and back" shape this directory's Responsibilities
section describes.

## Limitations
One document as of Phase 15. Additional cross-cutting guides are added
as a real need for one appears — not speculatively.

## Future improvements
- If doc volume grows, consider a docs site generator (e.g. Docusaurus,
  Mintlify) — decide via ADR, don't default to one.
