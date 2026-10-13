# platform-standards

## Purpose
A real, product-facing `KnowledgeBase` any product built on Avishkar OS
can import to give its own agents awareness of this platform's own
conventions — the first concrete shelf artifact under `knowledge/`
(Phase 14), rather than only an example living inside
`factories/knowledge-factory`.

## Responsibilities
- Ingest genuine excerpts from this repository's own `STANDARDS.md`
  (engineering principles, documentation templates, security
  checklist, naming conventions, commit discipline) into a real
  `KnowledgeBase`.
- Stay in sync with `STANDARDS.md` — a change there that changes one
  of these five excerpts should update the matching document here in
  the same PR.

## Architecture
`build_platform_standards_kb() -> KnowledgeBase` — ingests five
documents (`engineering-principles`, `documentation-templates`,
`security-checklist`, `naming-conventions`,
`commit-and-review-discipline`) using `knowledge-factory`'s real
`KnowledgeBase`/`HashingEmbedder` pipeline (Phase 6). No new
architecture — this module only supplies content.

## Interfaces
`build_platform_standards_kb() -> KnowledgeBase`. Callers use the
returned `KnowledgeBase`'s own `.search(query, top_k=5)`, or wrap it
via `knowledge-factory`'s `as_tool()` to register it on any
`ChiefDomainAgent`'s `ToolRegistry`.

## Dependencies
`core/`, `factories/agent-factory` (transitively, via
`avishkar_knowledge`), `factories/knowledge-factory`.

## Inputs
None at call time — the five documents are fixed, real excerpts
authored alongside `STANDARDS.md`.

## Outputs
A ready-to-search `KnowledgeBase`.

## Examples
`python knowledge/platform-standards/examples/quickstart.py` — loads
the KB and runs two real searches (engineering principles, security
guidance), printing the matched document and score.

## Limitations
Five documents today — a deliberately small, high-signal set, not a
full mirror of `STANDARDS.md`/`ARCHITECTURE.md`. `HashingEmbedder`'s
known ranking-quality limitations (see
`factories/knowledge-factory/README.md`) apply here too: use
distinctive query vocabulary.

## Future Roadmap
- Expand to cover `ARCHITECTURE.md`'s dependency-direction rules and
  `CLAUDE.md`'s Master Constitution once a real product needs an agent
  to reason about those specifically.
- A lint/CI check flagging when `STANDARDS.md` changes without a
  matching update here.
