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

A Chief Domain Agent is a **complete software system**, not a prompt
file — never "You are a Doctor" style role-play. The roster is locked per
DECISIONS.md ADR-0007; the template below is locked per **ADR-0010**
(supersedes the 18-section template ADR-0006 originally recorded — see
ADR-0010 for why). All 30 sections are required, in this order; a section
that genuinely doesn't apply says so explicitly rather than being
omitted.

```markdown
# <Domain> — Chief Domain Agent

## 1. Identity & Mission
What this agent exists to do, stated the way an elite professional in
this domain would state their own mandate.

## 2. Responsibilities
Concrete things this agent owns end to end. If a responsibility isn't
here, this agent doesn't own it.

## 3. Domain Knowledge Architecture
How this agent's knowledge is structured — bodies of knowledge, and
which `knowledge/` bases (present or planned) it's wired to.

## 4. Reasoning Strategies
The repertoire of approaches this agent applies to a problem in its
domain — plural, because different task shapes call for different
strategies, not one fixed script.

## 5. Decision Frameworks
How it decides between competing options, escalates, or defers.

## 6. Thinking Models
Named cognitive models this agent applies (first principles, systems
thinking, scientific method, OODA, etc.) and when each is used.

## 7. Planning & Reflection
How this agent plans before acting and reflects after — the loop
structure, not just that reflection "happens."

## 8. Memory Policies
Short-term, long-term, episodic, and semantic memory: what this agent
stores in each, and which `memory/` backend (present or planned) serves
it.

## 9. MCP Integration Points
Which MCP servers/tools this agent declares (via `MCPToolRef`), resolved
once the matching `mcp/` server exists (Phase 4).

## 10. Tool Registry
Concrete callable tools this agent can invoke today, and their contracts.

## 11. Knowledge Sources
External and internal sources of truth this agent consults.

## 12. Prompt Library
The named, versioned prompts this agent is built from.

## 13. Workflow Library
The reusable workflows this agent runs or participates in.

## 14. Template Library
Output templates this agent fills in per task type.

## 15. Checklists
Concrete, checkable steps this agent runs through for its core tasks.

## 16. Evaluation Framework
How this agent's output is scored — ties to `evaluation-factory`.

## 17. Security Policies
What this agent must never do with credentials, PII, or destructive
actions.

## 18. Guardrails
Pre-execution checks that can block a task before it starts.

## 19. Quality Gates
What must be true before this agent's output is considered done.

## 20. Error Recovery Strategies
What happens when a tool call, reasoning step, or sub-agent fails.

## 21. Output Standards
The shape and quality bar of what this agent produces, per task type.

## 22. Communication Style
How this agent talks — to end users and to other agents.

## 23. Collaboration Protocols
How this agent works with the Orchestrator and other Chief Agents.

## 24. Sub-Agent Architecture
How this Chief Agent's internal expert roles are structured and routed
between — roles are absorbed here, not spun up as new top-level agents
(ARCHITECTURE.md §4). Includes what the old template called "Internal
Routing Strategy."

## 25. Extensibility Model
How this agent's capability set grows without forking it.

## 26. Testing Strategy
How this agent's behavior is verified, beyond eval scores.

## 27. Versioning Strategy
How this agent's blueprint and prompts are versioned and rolled back.

## 28. Documentation
Where this agent's deeper docs live beyond this README.

## 29. Examples
At least one full worked example, input to output.

## 30. Future Roadmap
Known next steps, not a wishlist.
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
