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

## 2. Documentation templates — three tiers (see DECISIONS.md ADR-0006)

Which template applies depends on *what* is being documented, not
preference. No module/framework/agent ships without the matching template
filled in honestly — an empty "Purpose"/"Vision"/"Mission" means it isn't
ready to exist yet.

### 2.1 Module template — shelf packages & simple directories

Use for a single package under a library shelf (one agent's package, one
MCP server, one memory backend) and plain directories like `docs/`.

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

## Interfaces
The concrete API/contract other modules call — function/class signatures
or endpoint shapes, not prose. If it has no public interface yet, say so.

## Dependencies
What it requires from the rest of the platform (ideally: only `core/`).

## Inputs
What it consumes — types/schemas, not just names.

## Outputs
What it produces.

## Examples
At least one runnable/copy-pasteable example.

## Limitations
What it deliberately doesn't do yet, or won't do.

## Future Roadmap
Known next steps, not a wishlist.
```

### 2.2 Framework template — every `factories/*`, `core/`, `router/`

A Framework is a factory (or platform-wide capability) documented and
built to this fuller bar — not a different kind of folder, see ADR-0005.

```markdown
# <Name> Framework

## Vision
What this framework makes possible platform-wide, and why it must be a
framework (reusable, extensible) rather than a one-off implementation.

## Architecture
How it's built internally, including its major components and how they
fit together. Diagram if it clarifies more than it costs.

## Folder Structure
The layout inside this framework's own directory, and (if it produces a
shelf) the layout of what it produces.

## Naming Standards
Any naming conventions specific to this framework's artifacts, beyond the
platform-wide rules in §3.

## Interfaces
The concrete API/contract this framework exposes to its consumers
(agents, products, other frameworks) — signatures, not prose.

## Extension Model
How someone adds a new capability *through* this framework (a new agent
blueprint type, a new prompt category, a new graph pattern) without
modifying the framework's core.

## Examples
At least one runnable/copy-pasteable example of using this framework end
to end.

## Best Practices
What good usage of this framework looks like.

## Anti-Patterns
Specific, named misuses to avoid — and what to do instead.

## Future Roadmap
Known next steps, not a wishlist.
```

### 2.3 Chief Domain Agent template — every `agents/*`

A Chief Domain Agent is a complete engineering asset, not a prompt file.
The roster is locked per DECISIONS.md ADR-0007.

```markdown
# <Domain> — Chief Domain Agent

## Mission
What this agent exists to do, stated the way an elite professional in
this domain would state their own mandate.

## Capabilities
Concrete things this agent can do, not a vibe.

## Knowledge Areas
The bodies of knowledge this agent draws on (and, where relevant, which
`knowledge/` bases it's wired to).

## Reasoning Strategy
How this agent thinks through a problem in its domain — its default
approach, not a specific answer.

## Decision Framework
How it decides between competing options, escalates, or defers.

## Tools
What it can act with — see MCP Integrations below for tool delivery.

## MCP Integrations
Which `mcp/` servers this agent mounts, and why.

## Memory Usage
Which `memory/` backends it reads/writes, and what it stores in each
(short-term, long-term, episodic).

## Prompt Templates
The `templates/prompts/` entries this agent is built from.

## Checklists
Concrete, checkable steps this agent runs through for its core tasks.

## Reusable Workflows
Which `workflows/` this agent participates in.

## Output Formats
The shapes of what this agent produces, per task type.

## Quality Gates
What must be true before this agent's output is considered done — ties
to `evaluation-factory`.

## Examples
At least one full worked example, input to output.

## Failure Modes
Known ways this agent gets it wrong, and how that's caught.

## Limitations
What this agent deliberately does not attempt.

## Future Extensions
Known next steps, not a wishlist.

## Sub-Agent Architecture
How this Chief Agent's internal expert roles are structured — roles are
absorbed here, not spun up as new top-level agents (ARCHITECTURE.md §4).

## Internal Routing Strategy
How this agent decides which internal expert role handles a given
request.
```

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
