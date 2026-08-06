# Standards

Concrete, checkable rules. [ARCHITECTURE.md](./ARCHITECTURE.md) explains
*why* the system is shaped this way; this document defines *how* code and
docs are written inside it. When the two ever conflict, ARCHITECTURE.md
wins and this file gets fixed.

## 1. Engineering principles (non-negotiable)

SOLID · Clean Architecture · DDD where it earns its complexity · DRY · KISS
· YAGNI · composition over inheritance · convention over configuration ·
documentation-first · reusable-first · automation-first · security-first ·
AI-first · local-first where appropriate.

In practice, before writing code, ask in order:
1. Does this already exist somewhere in the platform? (DRY)
2. Am I building the simplest thing that satisfies the actual requirement,
   not the imagined future one? (KISS / YAGNI)
3. Can a second product use this unmodified or via config? (reusable-first)
4. Is the responsibility of this module still exactly one sentence? (SOLID-S)

## 2. Every module needs a README with this exact template

```markdown
# <Module Name>

## Purpose
Why this exists, in one paragraph.

## Responsibilities
What this module owns. Bullet list. If a responsibility isn't here, this
module doesn't own it — say where it lives instead.

## Architecture
How it's built internally. Diagram (mermaid or ASCII) if it clarifies more
than it costs.

## Inputs
What it consumes — types/schemas, not just names.

## Outputs
What it produces.

## Dependencies
What it requires from the rest of the platform (ideally: only `core/`).

## Examples
At least one runnable/copy-pasteable example.

## Limitations
What it deliberately doesn't do yet, or won't do.

## Future improvements
Known next steps, not a wishlist.
```

No module ships without this. A module with an empty "Purpose" is a module
that shouldn't exist yet.

## 3. Naming conventions

- Directories: `kebab-case` (e.g. `agent-factory`, `starter-kit-factory`).
- Python packages/modules: `snake_case`. TypeScript files: `kebab-case.ts`.
- Classes: `PascalCase`. Functions/variables: `snake_case` (Python) or
  `camelCase` (TS), matching the language's own convention — never invent a
  third style per file.
- Factories are always named `<domain>-factory`. Their output shelves use
  the plural of what they produce (`agents/`, not `agent/`).
- No abbreviations that aren't industry-standard (`mcp`, `ai` are fine;
  `wf` for workflow is not).

## 4. Documentation

- Every public function/class: docstring stating purpose, params, return,
  and raised errors — not a restatement of the signature.
- Every design decision that isn't obvious from the code gets an ADR in
  [DECISIONS.md](./DECISIONS.md), not just a code comment.
- Comments explain *why*, never *what* (the code already says what).

## 5. Testing & evaluation

- New factory output types get at least one scaffold-and-validate test in
  the owning factory before the factory is considered "done."
- Agents and prompts are evaluated through `evaluation-factory`, not ad hoc
  scripts — if an eval need doesn't fit the harness yet, that's a gap in
  `evaluation-factory`, fix it there.

## 6. Security

- No secrets, API keys, or credentials committed, ever — `.env.template`
  documents required variables; `.env` is git-ignored.
- Every MCP server and agent tool that touches external systems goes
  through `security-factory`'s guardrail/threat-model checklist before it's
  marked reusable.

## 7. Commit & review discipline

- Commits are scoped to one logical change; message states *what* and,
  where non-obvious, *why*.
- Structural or dependency-direction changes (§5 of ARCHITECTURE.md)
  require an ADR *before* the PR, not after.
- No file is added "just in case." If you can't fill in its README's
  Purpose section honestly, don't create it yet.
