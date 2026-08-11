# Decisions

Append-only architecture decision log. Every ADR states the decision,
context, and the trade-off accepted — not just the conclusion. Never edit
or delete a past ADR to reflect new thinking; add a new one that supersedes
it and say so.

Format: `ADR-NNNN: Title` · Status · Date · Context · Decision · Alternatives
considered · Consequences.

---

## ADR-0001: Write structure and standards before implementation

**Status:** Accepted · **Date:** 2026-08-06

**Context:** Avishkar OS is meant to power every current and future
Avishkar Labs product for years. Starting with code and backfilling
architecture tends to produce structure that fits whatever was built first,
not what the platform actually needs.

**Decision:** Scaffold the full repository structure, root governance docs
(this file, ARCHITECTURE.md, STANDARDS.md, ROADMAP.md), and CLAUDE.md
before any factory or module is implemented. Every directory ships with a
README stating its contract even while empty.

**Alternatives considered:** Build the first factory (agent-factory) end to
end, derive structure from what it needed. Rejected — optimizes for one
factory's shape, risks the same redundancy problem seen in ADR-0002.

**Consequences:** Slower to first working code; much lower risk of a
costly restructure once products depend on this repo. Structure docs must
be kept honest — if a directory's README purpose stops matching reality,
that's a doc bug to fix immediately, not eventually.

---

## ADR-0002: `factories/` are generators; top-level dirs are the built library

**Status:** Accepted · **Date:** 2026-08-06

**Context:** The requested repository tree includes a `factories/`
directory *and* separate top-level directories (`agents/`, `templates/`,
`workflows/`, `knowledge/`, `memory/`, `router/`, `mcp/`, `langgraph/`,
`automation/`, `starters/`) whose names overlap with factory names listed
in the platform's capability list (Agent Factory, Template Factory,
Workflow Factory, etc.). Taken literally, this reads as duplication: two
places for "agents," two for "workflows."

**Decision:** Treat them as two different concerns, not a duplication:
`factories/<x>-factory/` holds the *generator* — the tooling, blueprints,
and CLI that produce a new instance of X. The matching top-level directory
holds the *finished, reusable output* of that factory, hardened and ready
for products to consume directly. See ARCHITECTURE.md §2 for the full
rationale and the table of which factories have a matching shelf.

**Alternatives considered:**
1. *Collapse into `factories/` only, no top-level shelves* — rejected:
   forces every consumer to know which factory produced an artifact just
   to find it, and mixes "tool that builds things" with "things" in one
   directory, violating single-responsibility at the folder level.
2. *Collapse into top-level dirs only, no `factories/`* — rejected: loses
   the reusable *process* of building new agents/prompts/workflows as a
   first-class, documented capability, which the mission statement
   explicitly calls for ("Can it become a factory?").

**Consequences:** Every factory's README must clearly state what it
produces and where that output lands (or explicitly state it has no
top-level shelf, and why — see ARCHITECTURE.md §2). Reviewers should reject
any PR that puts generator logic in a shelf directory or hand-written
one-off artifacts in a factory directory.

---

## ADR-0003: Avishkar OS gets its own git repository, separate from the user's home-directory repo

**Status:** Accepted · **Date:** 2026-08-06

**Context:** At scaffold time, `C:\Users\Administrator` was itself the root
of an existing git repository also tracking an unrelated project
(`Documents\robot_ai`) with a large set of uncommitted changes. Nesting
Avishkar OS inside that repository would entangle a flagship, decades-long
platform's history with an unrelated project's, and with anything else
that happens to live in the user's home directory.

**Decision:** Avishkar OS is its own repository, rooted at
`Desktop\Avishkar Labs\Avishkar-OS`, with independent git history. The
pre-existing home-directory repository was left untouched.

**Alternatives considered:** Commit into the existing home-directory repo.
Rejected by the user for exactly the reason above.

**Consequences:** Avishkar OS's history is clean from commit one. The
pre-existing home-directory repo (and what to do with `robot_ai`'s pending
changes) is a separate concern, out of scope here, and unaffected by this
work.

---

## ADR-0004: Default license is proprietary, not open source

**Status:** Accepted · **Date:** 2026-08-06

**Context:** Avishkar OS is the core engineering platform behind every
Avishkar Labs product — it is Avishkar Labs' primary competitive asset. No
open-source intent was stated.

**Decision:** Default to "All Rights Reserved" (see LICENSE), not an
OSS license like MIT/Apache-2.0.

**Alternatives considered:** MIT — rejected as the default because it
would permit unrestricted external use/forking of the platform's core IP
by default; open-sourcing specific factories later remains possible and
should be a deliberate, case-by-case ADR, not the starting posture.

**Consequences:** If any factory or module is later open-sourced, that
requires its own ADR and a license change scoped to that piece (or the
whole repo, if that's the call) — not a silent LICENSE edit.

---

## ADR-0005: Add Documentation Framework as a 14th factory; "Framework" is the richer documentation tier of a factory, not a rename

**Status:** Accepted · **Date:** 2026-08-08

**Context:** The Master Build Directive lists 15 "Frameworks" platform-wide,
which maps almost 1:1 onto the 13 factories + `core/` + `router/` already
built (ADR-0002), with two differences: the directive's list omits Starter
Kit (already built and committed as `factories/starter-kit-factory`), and
adds a new "Documentation Framework" with no prior equivalent — `docs/`
existed only as a plain directory, with no generator or platform-wide
enforcement behind it. The directive also uses "Framework" where prior
ADRs used "Factory," and describes a richer documentation bar (Vision,
Folder Structure, Naming Standards, Extension Model, Best Practices,
Anti-Patterns) than STANDARDS.md §2 required at the time.

**Decision:**
1. Keep Starter Kit Framework as-is — nothing already built and committed
   gets deleted to match a list that most plausibly omitted it by
   oversight, not deliberate cut.
2. Add `factories/documentation-factory` ("Documentation Framework") as a
   genuinely new, 14th factory. Unlike `template-factory` (which produces
   reusable *content* templates — PRD, API doc, architecture doc shapes
   products fill in), Documentation Framework enforces the platform's
   *own* documentation compliance: the README templates in
   [STANDARDS.md](./STANDARDS.md) §2, ADR process tooling, and doc-coverage
   checks (every folder has meaningful docs — see [ROADMAP.md](./ROADMAP.md)
   Phase 0's CI scaffold item). This brings the total to 16 top-level
   modules (13 factories + Documentation Framework = 14 factories, +
   `core/` + `router/` = 16).
3. "Framework" and "Factory" refer to the same thing at different
   resolution — a Framework is a factory documented and built to the
   fuller bar defined in ADR-0006, not a folder rename. See ADR discussion
   in the chat log of 2026-08-08 for the explicit user approval of this
   reading over a literal `factories/` → `frameworks/` rename.

**Alternatives considered:**
1. *Fold Starter Kit into Project Framework, hit exactly 15* — rejected by
   the user; keeps the directive's count but discards working, committed
   structure for a cosmetic match.
2. *Rename `factories/` → `frameworks/` and every `<x>-factory` →
   `<x>-framework` folder* — rejected by the user; mechanical rename
   touching cross-links in 24 already-committed files with no functional
   change, and loses more precise technology-specific names (`n8n-factory`
   is more precise than a generic `automation-factory` would be if a
   second automation engine is ever added).

**Consequences:** ARCHITECTURE.md §3's factory table gains a
`documentation-factory` row. STANDARDS.md gains the Documentation
Framework's own doc-coverage responsibility. Future references to "the 16
frameworks" and "the 13 factories" both refer to consistent, disjoint-free
counts — see ARCHITECTURE.md for the canonical list.

---

## ADR-0006: Three-tier documentation template — Module, Framework, Chief Domain Agent

**Status:** Accepted · **Date:** 2026-08-08

**Context:** The original module README template (STANDARDS.md §2, written
under ADR-0001) was one-size-fits-all: Purpose, Responsibilities,
Architecture, Inputs, Outputs, Dependencies, Examples, Limitations, Future
improvements. The Master Build Directive asks for three genuinely
different depths of documentation depending on what's being documented: a
plain module/shelf package, a Framework (a factory or platform-wide
capability like Core Engine or AI Router), and a Chief Domain Agent (a
complete engineering asset, not a prompt file).

**Decision:** STANDARDS.md §2 now defines three templates instead of one:

1. **Module template** (unchanged in spirit, `Interfaces` added): Purpose,
   Responsibilities, Architecture, Interfaces, Dependencies, Inputs,
   Outputs, Examples, Limitations, Future Roadmap. Used for shelf packages
   (a single agent's package, a single MCP server, a single memory
   backend) and simple directories like `docs/`.
2. **Framework template** (new, richer): Vision, Architecture, Folder
   Structure, Naming Standards, Interfaces, Extension Model, Examples,
   Best Practices, Anti-Patterns, Future Roadmap. Used for every
   `factories/*` entry, plus `core/` ("Core Engine Framework") and
   `router/` ("AI Router Framework").
3. **Chief Domain Agent template** (new, most demanding): Mission,
   Capabilities, Knowledge Areas, Reasoning Strategy, Decision Framework,
   Tools, MCP Integrations, Memory Usage, Prompt Templates, Checklists,
   Reusable Workflows, Output Formats, Quality Gates, Examples, Failure
   Modes, Limitations, Future Extensions, Sub-Agent Architecture, Internal
   Routing Strategy. Used for every entry under `agents/`.

Existing READMEs written under the old single template (all 13 factory
READMEs, `core/`, `router/`) are upgraded to the Framework template as
each framework is actually built, per the one-framework-at-a-time
execution discipline (ROADMAP.md) — not rewritten in bulk immediately,
to avoid documentation churn racing ahead of implementation.

**Alternatives considered:** Keep one universal template and let each
factory add ad hoc extra sections — rejected: produces inconsistent docs
across factories, defeats the point of "every framework must include
Vision, Architecture, Folder Structure..." being a checkable standard
rather than a suggestion.

**Consequences:** Any new module/framework/agent must be checked against
the correct template before being considered documented. STANDARDS.md §2
is the single source of truth for all three; this ADR records why there
are three, not one.

---

## ADR-0007: Chief Domain Agent roster locked at 10 domains + Orchestrator

**Status:** Accepted · **Date:** 2026-08-08

**Context:** ARCHITECTURE.md §4 (ADR-0002-era) stated the *principle*
("build only reusable Chief Domain Agents, not sprawl") without a concrete
roster. The Master Build Directive supplies an explicit, concrete list.

**Decision:** The initial Chief Domain Agent roster for `agents/` is
locked to exactly these 11 entries — 10 domain agents plus one
Orchestrator that decides which domain agents collaborate on a given
task:

1. Software & AI Engineering
2. Medical & Healthcare
3. Legal & Compliance
4. Startup, Business & Product
5. Education & Knowledge
6. Research & Intelligence
7. Finance & Economics
8. Government & Public Policy
9. Human Development & Psychology
10. Creative & Media
11. Orchestrator

Each is built to the Chief Domain Agent template (ADR-0006) — a complete
engineering asset (reasoning strategy, decision framework, tools, MCP
integrations, memory usage, quality gates, failure modes, sub-agent
architecture, internal routing), not a prompt file. New expert *roles*
within a domain are absorbed into the matching Chief Agent (per
ARCHITECTURE.md §4's existing absorption test); a genuinely new *domain*
outside this list requires its own ADR before a 12th agent is added.

**Alternatives considered:** Leave the roster open-ended, add domains
organically as products need them. Rejected — the directive explicitly
enumerates the roster as a locked design decision, not a starting
suggestion; an open-ended list is exactly the "agent sprawl" ARCHITECTURE.md
§4 already warns against.

**Consequences:** `agents/` will contain up to 11 top-level packages, no
more, until a new ADR explicitly grows the list. None are implemented yet
— they are built one at a time, in whatever order the Agent Framework
phase of ROADMAP.md schedules, each fully to the template before the next
starts.

---

## ADR-0008: Core Engine Framework — polyglot contract, Python reference implementation

**Status:** Accepted · **Date:** 2026-08-08

**Context:** Phase 1 (ROADMAP.md) requires building Core Engine
Framework — config, logging, event bus, module registry — the substrate
every other framework depends on. No implementation language had been
chosen for the platform. Avishkar Labs' products and future frameworks
plausibly span ecosystems (LangGraph/agent tooling leans Python; MCP's
reference SDK and n8n lean Node/TypeScript), so committing Core Engine to
a single language risks forcing every future framework into that
language's ecosystem regardless of fit.

**Decision:** Core Engine's four capabilities (Config, Logger, EventBus,
ModuleRegistry) are specified as a language-agnostic contract —
[`core/CONTRACT.md`](../core/CONTRACT.md) for method signatures/semantics,
[`core/schemas/`](../core/schemas/) (JSON Schema) for shared data shapes
(config resolution, log record, event envelope, module manifest). Python
ships first as the reference implementation
([`core/python/avishkar_core/`](../core/python/avishkar_core/)),
stdlib-only (no third-party dependencies) so it stays trivially
installable and auditable. Other language implementations (starting with
TypeScript, likely needed once `mcp-factory`/`n8n-factory` are built) must
satisfy the same contract, not invent their own — conformance is judged
against `CONTRACT.md` and the schemas, not against the Python source.

**Alternatives considered:**
1. *Python-only* — rejected: cheapest now, but forces every future
   framework (including ones that fit TypeScript better, e.g. MCP
   servers) into Python or into calling out to a Python process, which is
   exactly the kind of premature constraint a decades-long platform
   shouldn't lock in during Phase 1.
2. *TypeScript-only* — rejected: same objection in reverse; would force
   Python-native agent/eval tooling (LangGraph, most ML/eval libraries)
   into a worse position.
3. *Full polyglot from day one (Python + TS reference implementations
   both shipped now)* — rejected as Phase 1 scope: doubles the surface
   area to build, review, and keep in sync before a single framework is
   locked. The contract is designed to make adding a second
   implementation later straightforward, without that cost now.

**Consequences:** Every other framework's "Interfaces" section
(STANDARDS.md §2.2) that depends on Core Engine must be checkable against
`CONTRACT.md`, not just against the Python package. Adding a second
language implementation is expected, not hypothetical — it does not
require a new ADR, only conformance review against the existing contract.
The contract itself changing (a new capability, a breaking signature
change) does require an ADR, since every framework depends on it.

---

## ADR-0009: Build order reordered — Router, Agent, MCP, Memory, Knowledge, Workflow, then Prompt/Template/Starter Kit

**Status:** Accepted · **Date:** 2026-08-08

**Context:** ROADMAP.md (post-ADR-0001/0002) sequenced Phase 2 as
"Routing & Memory" (`router/`, `memory-factory`, `knowledge-factory`
together) and Phase 3 as "Orchestration & Automation"
(`langgraph-factory`, `n8n-factory`, `workflow-factory`, `mcp-factory`
together). The user issued an explicit, more granular build order instead:
Core (done) → AI Router → Agent Framework (where the 11 Chief Domain
Agents begin) → MCP Framework → Memory Framework → Knowledge Framework →
Workflow Framework → Prompt + Template + Starter Kit Frameworks, one at a
time, each production-ready before the next starts.

**Decision:** Adopt the user's explicit order. Rationale for the order
itself (as given): AI Router must exist before Agent Framework since every
agent needs model routing; MCP Framework comes before Memory/Knowledge
since agent-usable tool integration is more foundational than retrieval;
Workflow Framework comes after because it composes agents, memory, and
knowledge together; Prompt/Template/Starter Kit come last as
product-enablement polish built on everything else. `langgraph-factory`,
`n8n-factory` (Automation), `project-factory`, `evaluation-factory`,
`security-factory`, and `documentation-factory` are **not yet scheduled**
— ROADMAP.md marks them "deferred, order TBD" rather than silently
assigning them a slot, per STANDARDS.md's rule against files/plans
existing without a stated purpose.

**Alternatives considered:** Keep the original Phase 2/3 grouping.
Rejected — superseded by explicit user direction; the original grouping
was itself a scaffold-time default (ADR-0001 era), not a decision anyone
had deliberately committed to over this one.

**Consequences:** ROADMAP.md rewritten to the new phase list. Every
future "next framework" question is answered by that list, in order,
until the deferred set is explicitly scheduled via a future ADR.

---

## ADR-0010: Chief Domain Agent template expanded from 18 to 30 sections; Agent Framework built as a runtime, not a prompt library

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ADR-0006 locked an 18-section Chief Domain Agent template
(Mission, Capabilities, Knowledge Areas, Reasoning Strategy, Decision
Framework, Tools, MCP Integrations, Memory Usage, Prompt Templates,
Checklists, Reusable Workflows, Output Formats, Quality Gates, Examples,
Failure Modes, Limitations, Future Extensions, Sub-Agent Architecture,
Internal Routing Strategy). For Phase 3 (Agent Framework), the user gave
an explicit, more demanding 30-section specification and explicitly
rejected "simple role prompts" ("You are a Doctor" style) in favor of
"a complete software system." This is a direct instruction from the
architecture's owner, not a change I am proposing — recorded here per
STANDARDS.md §7 and CLAUDE.md's rule that structural changes need an ADR,
not silent drift.

**Decision:** STANDARDS.md §2.3's Chief Domain Agent template is replaced
with the user's 30-section list, verbatim and in the given order: Identity
& Mission, Responsibilities, Domain Knowledge Architecture, Reasoning
Strategies, Decision Frameworks, Thinking Models, Planning & Reflection,
Memory Policies, MCP Integration Points, Tool Registry, Knowledge
Sources, Prompt Library, Workflow Library, Template Library, Checklists,
Evaluation Framework, Security Policies, Guardrails, Quality Gates, Error
Recovery Strategies, Output Standards, Communication Style, Collaboration
Protocols, Sub-Agent Architecture, Extensibility Model, Testing Strategy,
Versioning Strategy, Documentation, Examples, Future Roadmap. The old
template's "Internal Routing Strategy" section is folded into "Sub-Agent
Architecture" (#24) rather than kept separate, since the new list doesn't
name it independently and its content belongs there.

Consequently, `agent-factory` ("Agent Framework") is built as an actual
**runtime** — a reasoning-loop engine, memory/tool/thinking-model
primitives, and an Orchestrator — not a generator that only produces
Markdown. A Chief Domain Agent built on it is a small Python package
(blueprint + domain module) plus its 30-section README, not a prompt
string. The framework itself must support single-agent, multi-agent,
hierarchical, and swarm execution, human-in-the-loop approval gates,
reflection loops, and self-evaluation, with typed extension seams for MCP
(`MCPToolRef`, resolved once `mcp-factory` — Phase 4 — exists) and
LangGraph (a step function shaped to be wrappable as a LangGraph node,
without an actual LangGraph dependency yet — `langgraph-factory` remains
deferred per ADR-0009). Adding a new Chief Domain Agent must require zero
changes to `agent-factory`'s own source — only a new blueprint + domain
module.

**Alternatives considered:** Keep ADR-0006's 18-section template and treat
the new 30-item list as supplementary guidance. Rejected — the user was
explicit that role-prompt-style agents are unacceptable and gave a
complete, ordered replacement list, not an addendum; treating it as
optional would under-deliver against a direct instruction.

**Consequences:** All future Chief Domain Agents (10 remaining +
Orchestrator) are documented to the 30-section template. No prior agent
docs exist yet to migrate (Phase 3 is the first agent built). The
Framework template (STANDARDS.md §2.2) and Module template (§2.1) are
unaffected — this ADR only supersedes the agent tier.

---

## ADR-0011: `mcp-factory` becomes the Universal Integration Framework (MCP-first, protocol-agnostic); LangGraph and Agent Framework integration delivered without new hard dependencies or touching locked code

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ROADMAP.md Phase 4 and ARCHITECTURE.md's factory table
named this framework narrowly: "MCP Framework (`mcp-factory`) — MCP
server generator + security-checklist-by-default scaffolding." The user
directed a materially larger scope for Phase 4: a protocol-agnostic
"Universal Integration Framework" with MCP as its first-class
implementation, plus a 12-field universal tool contract, a tool runtime
(retry/timeout/logging/metrics/cost tracking), integration policies
(security/access-control/approval/sandboxing/trust level), memory
integration, Agent Framework integration ("agents request capabilities,
not implementations"), AI Router integration (best model/protocol/tool/
execution path), and LangGraph-shaped reusable nodes — explicitly "not
only an MCP wrapper." Three architectural questions had to be resolved
before writing code, all direct instructions from the architecture's
owner rather than a change I'm proposing on my own initiative:

1. Does this warrant a new, 15th factory, or does it live in the
   already-locked `mcp-factory` slot (ADR-0005's factory table)?
2. "LangGraph Integration" asks for real reusable nodes, but
   `langgraph-factory` is explicitly deferred (ADR-0009) — does this
   un-defer it?
3. "Agent Integration" asks agents to consume tools without knowing the
   protocol — but `agent-factory` (Phase 3) is locked; can this framework
   satisfy that requirement without reopening Phase 3?

**Decision:**

1. **No new factory.** `factories/mcp-factory/` keeps its folder name
   and its ADR-0005 factory-table slot; its *Framework identity* is
   elevated to "Universal Integration Framework" — the same
   folder-stays/scope-deepens move ADR-0005 already established for
   Documentation Framework, and structurally identical to how AI Router
   (Phase 2) is provider-agnostic with `AnthropicProvider` as its first,
   not only, adapter. `ProtocolAdapter` is the abstraction; `MCPAdapter`
   is the first-class implementation built to production quality; a
   second real adapter (`RESTAdapter`, stdlib-only) is built alongside it
   specifically to prove the abstraction is genuine and not an
   MCP-shaped wrapper with one implementation. GraphQL, Python SDKs, CLI,
   Databases, Filesystems, and Webhooks are documented extension points
   (README.md Extension Guide) with no scaffolded files — an unimplemented
   adapter is not built as an empty stub, per the explicit instruction
   against placeholder files and per STANDARDS.md's existing rule against
   files without a stated, truthful purpose.
2. **LangGraph integration ships now, without un-deferring
   `langgraph-factory` and without a `langgraph` dependency.** A LangGraph
   node is, by the framework's own public contract, a plain
   `Callable[[State], PartialState]`. This framework's `langgraph_nodes`
   module ships real, tested functions matching that shape (tool
   execution, MCP call, REST call, retry, approval, logging) that a
   caller wires into their own `StateGraph` — genuinely useful today,
   with zero import of the `langgraph` package. `langgraph-factory`
   (ADR-0009's deferred list) remains about something larger — LangGraph-
   *native* orchestration as a first-class execution engine — and stays
   deferred.
3. **Agent Framework integration ships as a converter this framework
   owns, not a change to `agent-factory`.** `agent_bridge.py` resolves an
   `avishkar_agent.MCPToolRef` (already public, already part of
   `agent-factory`'s locked contract as a typed placeholder — see
   `agent-factory/CONTRACT.md` §4) against a real `UniversalToolRegistry`,
   and exposes capability-based lookup so a Chief Domain Agent can request
   "a tool with capability X" without naming a protocol. This is a new
   *consumer* of `agent-factory`'s existing public types, not an edit to
   `agent-factory`'s source — Phase 3's lock is untouched. Wiring an
   actual Chief Domain Agent's `ToolRegistry` to delegate through this
   bridge by default is left to that agent's own domain module (a
   one-line change whenever a real MCP server exists to point at) —
   tracked as Future Roadmap, not done speculatively here.

**Alternatives considered:**
1. *Scaffold a new `integration-factory`, retire `mcp-factory`* —
   rejected: grows the locked 16-Framework count for a rename, and
   duplicates work already done under the `mcp-factory` name across
   ARCHITECTURE.md, ROADMAP.md, and DECISIONS.md.
2. *Un-defer `langgraph-factory` and add a real `langgraph` dependency
   now* — rejected: the user's ask is specifically for reusable *nodes*,
   which the plain-function contract satisfies without the dependency;
   pulling in a full orchestration engine dependency for six wrapper
   functions is exactly the kind of premature dependency STANDARDS.md §1
   warns against.
3. *Modify `agent-factory`'s `ToolRegistry`/`MCPToolRef` to import this
   framework directly* — rejected: `agent-factory` is Phase 3, already
   locked and tested; a dependency should be added by the consumer
   reaching for it (this framework depending on `agent-factory`'s types,
   §7 of CONTRACT.md), not by reopening and re-testing a locked framework
   for a capability it already exposed a seam for.

**Consequences:** `factories/mcp-factory` depends on `core/`, `router/`,
and `agent-factory` (for the bridge module only — every other module
stays dependency-free of `agent-factory`). Building the remaining 6
documented-but-unimplemented protocol adapters is real future work
tracked in README.md Future Roadmap, not a promise this ADR pretends is
already kept. A future ADR is required before `langgraph-factory` itself
is un-deferred as a scheduled phase.

---

## ADR-0012: Execution Mode (Phases 5–15) — roster confirmed at 11, one-ADR-per-phase discipline relaxed to one-ADR-per-genuine-decision

**Status:** Accepted · **Date:** 2026-08-09

**Context:** The user authorized continuous, unattended execution through
Phase 15 (Memory, Knowledge, Workflow, Prompt, Template, Starter Kit,
Evaluation, Security Frameworks; the remaining 10 Chief Domain Agents;
a "Knowledge Library" population pass; Final Integration), stopping only
for decisions that genuinely require approval. Phase 13's roster named
"Science" alongside "Research & Intelligence" plus "Executive
Orchestrator" — apparently 12 agents against ADR-0007's locked 11. Asked
directly (the one interruption this ADR records): **confirmed** "Science"
is "Research & Intelligence" renamed, not a 12th domain — the roster
stays at 11 (10 domains + Orchestrator, "Executive Orchestrator" is a
cosmetic rename of the same locked seat, not a new one). No roster ADR
is needed; ADR-0007 stands unchanged in substance.

**Decision:** Proceed through Phases 5–15 without pausing between them.
Each phase still gets: real design, working code, a language-agnostic
contract where a new framework is introduced, passing tests, a runnable
example, honest documentation, a ROADMAP/CHANGELOG update, and its own
commit — the same bar Phases 1–4 set. What changes is pacing, not
quality: documentation prose is tighter (real content, less repetition
of already-established platform-wide context every framework already
inherits from CLAUDE.md/ARCHITECTURE.md/STANDARDS.md), and an ADR is
recorded only for a decision that's genuinely new or that reconciles an
ambiguity — not one per phase by default the way Phase 0–4 did while the
platform's own conventions were still being established.

**Alternatives considered:** Ask before every phase, as before. Rejected
per explicit instruction — the user named the one class of exception
(decisions requiring approval) and this session already exercised it
once (the roster question above).

**Consequences:** Phases 5–15 are logged here as they land, each with
its own commit. If a genuine fork appears mid-execution (an ambiguity a
default can't safely resolve, or a request to change already-locked
architecture), execution pauses for that one decision and then resumes —
consistent with every ADR in this log, not a new exception.

---

## ADR-0013: `workflow-factory` ships a plain-callable step engine; `langgraph-factory`/`n8n-factory` stay deferred; `RetryPolicy` reused a third time

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ROADMAP.md Phase 7 asks `workflow-factory` to compose
agents, memory, and knowledge into repeatable multi-step processes. Its
own README (written at scaffold time) speculated the workflow spec
would "compile to either a LangGraph graph... or an n8n flow" — but both
`langgraph-factory` and `n8n-factory` are explicitly deferred (ADR-0009),
and ADR-0011 already established the pattern for exactly this situation
when `mcp-factory` needed "LangGraph Integration" without un-deferring
`langgraph-factory`.

**Decision:** Reuse ADR-0011 §2's playbook rather than re-litigate it.
`avishkar_workflow`'s `Step.handler` is a plain
`Callable[[State], PartialState]` — LangGraph's own node contract — and
`WorkflowEngine` is a real, tested, in-process runner over a validated
`WorkflowSpec` graph, with zero import of `langgraph` or `n8n`. A caller
with `langgraph` installed can wire a spec's steps into their own
`StateGraph` today; nothing here blocks that, and nothing here pretends
to be LangGraph-native orchestration (a first-class execution engine),
which is what `langgraph-factory` remains reserved for. Composition with
the three earlier frameworks ships as `bridges.py` — `make_agent_step`,
`make_knowledge_search_step`, `make_memory_read_step`/
`make_memory_write_step` — each a consumer of that framework's already-
public types, touching no locked source (the same dependency-direction
discipline as ADR-0011 §3, now exercised a third time). `RetryPolicy` is
imported from `avishkar_integration` rather than redefined (`Tool`/
`MemoryPolicy` precedent, now also exercised a third time).

**Alternatives considered:**
1. *Un-defer `langgraph-factory` now, since a workflow engine is exactly
   what it was reserved for* — rejected: the user's Phase 5–15 list
   names `workflow-factory` specifically, not `langgraph-factory`;
   scheduling a deferred framework is explicitly gated on "a future ADR"
   per ADR-0009, which requires a decision to schedule it, not a
   convenient moment to fold it in.
2. *Redefine a workflow-local `RetryPolicy`* — rejected: identical
   shape to the one `avishkar_integration` already ships; redefining it
   would violate DRY for no benefit.

**Consequences:** `factories/workflow-factory` depends on `core/`,
`agent-factory`, `mcp-factory` (for `RetryPolicy` only), `memory-factory`,
and `knowledge-factory` — the widest dependency footprint of any
framework so far, which is expected: composition is its entire purpose.
A future ADR is still required before `langgraph-factory` or
`n8n-factory` themselves are scheduled.

---

## ADR-0014: `prompt-factory` ships its own `Scorer` seam instead of depending on the not-yet-built `evaluation-factory`; no new agent-factory bridge needed

**Status:** Accepted · **Date:** 2026-08-09

**Context:** `prompt-factory`'s own README (written at scaffold time)
listed `evaluation-factory` as a dependency — "every prompt needs a
scoring path before it's reusable." But the locked Phase 5–15 order
(ADR-0012) builds Prompt at Phase 8 and Evaluation at Phase 11 —
*after* Prompt. A hard dependency on a framework that doesn't exist yet
would either block Phase 8 or force building Evaluation out of order,
neither of which the locked order intends.

**Decision:** `prompt-factory` defines its own minimal scoring seam —
`Scorer = Callable[[str, EvalCase], float]` — with two real, useful
built-in scorers (`exact_match_scorer`, `keyword_presence_scorer`) and
real `evaluate_version`/`compare_versions` functions, genuinely useful
today for deterministic and keyword-bearing prompts. This is the same
"typed placeholder a later framework resolves" pattern `agent-factory`
used for `MCPToolRef` (ADR-0010), resolved by `mcp-factory` a full
phase later (ADR-0011) — Phase 11's `evaluation-factory` will supply
richer `Scorer` implementations (semantic similarity, LLM-graded,
regression-suite runners) that plug into the exact same
`evaluate_version` signature, with zero changes to `prompt-factory`.
Separately, no new Agent Framework bridge module was needed (contrast
`workflow-factory`'s `bridges.py`, ADR-0013): a rendered prompt is a
`str`, and `Task.input` has been `str` since Phase 3 — `prompt-factory`
is a pure producer of a type `agent-factory` already consumes.

**Alternatives considered:**
1. *Reorder Phases 8 and 11, building Evaluation first* — rejected: the
   user's Execution Mode phase list is explicit about the order; Prompt
   depending on Evaluation is this framework's own earlier (pre-lock)
   README speculation, not a requirement from the user.
2. *Have `prompt-factory` ship no scoring at all, deferring it entirely
   to Phase 11* — rejected: `compare_versions`/`evaluate_version` are
   real, small, and directly needed by this phase's own "diff/compare
   tooling between prompt versions" responsibility (README.md); shipping
   nothing here would under-deliver against that responsibility while
   waiting three phases for no real reason.

**Consequences:** `factories/prompt-factory` depends only on `core/` —
the narrowest dependency footprint of any framework since Phase 2,
appropriate for a framework whose job is producing versioned strings.
Phase 11 is now understood to *extend* this seam, not replace it.

---

## ADR-0015: `template-factory` wraps `avishkar_prompt.PromptVersion` directly instead of redefining a parallel validated-string type

**Status:** Accepted · **Date:** 2026-08-09

**Context:** `template-factory`'s own README (pre-Phase-9) described a
template as "structured files... with metadata (variables, ...)" —
structurally identical to what `prompt-factory` (Phase 8) already built
and locked as `PromptVersion`/`PromptVariable`/`render()`. Building a
second, parallel "content + declared variables" type for this framework
would duplicate validation logic (undeclared-placeholder detection,
required-variable enforcement) that already exists and is already
tested.

**Decision:** `TemplateFile(relative_path, spec: PromptVersion)` wraps
`prompt-factory`'s type directly rather than defining its own. This is
a step further than prior reuses (`RetryPolicy`, `Tool`, `MemoryPolicy`
were reused as leaf types passed through unchanged) — here a whole
composite type crosses a factory boundary and becomes a *field* of a
new type in the consuming framework. The dependency direction is still
the established one (Phase 9 depends on Phase 8's public types, not the
reverse); what's new is how tightly the reuse is woven in, which this
ADR records so it doesn't read as accidental coupling later.

**Alternatives considered:**
1. *Define a template-local `TemplateVariable`/content type* —
   rejected: identical shape and validation to `PromptVariable`/
   `PromptVersion`; would need to be kept in sync by hand forever for
   no behavioral difference.
2. *Have `template-factory` depend on `prompt-factory` only for the
   `render()` function, keeping its own variable-declaration type* —
   rejected: `render()`'s required-variable enforcement is meaningless
   without `PromptVersion`'s own construction-time validation; splitting
   them would silently drop the "undeclared placeholder" safety net this
   reuse is meant to preserve.

**Consequences:** `factories/template-factory` depends on `core/` and
`prompt-factory`. A future change to `PromptVersion`'s validation rules
automatically applies to every `TemplateFile` — intentional, and worth
remembering when `prompt-factory` is next touched.

---

## ADR-0016: `starter-kit-factory` ships one generic kit, not a named-product kit; generated `main.py` is real source code, not a serialized object graph

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ROADMAP.md's original Phase 10 text (written before
Execution Mode's phase split, ADR-0012) named an aspirational bullet:
"First real product... scaffolded from a starter kit and running on
Avishkar OS," with candidates Tryvanta / Humanify OS / GENESIS /
Muziclly / AI Atlas / Coupler. Building a kit shaped for one of those
means making product decisions (what the product does, what knowledge
it needs, what its agent's domain and mission actually are) that
CLAUDE.md's Master Constitution explicitly reserves for product repos,
not this platform: **"No business logic in the platform."** Separately,
composing an agent + memory + knowledge + workflow into a "portable"
kit ran into a real technical question: `WorkflowSpec`'s steps are
Python closures bound to specific runtime objects — there is no honest
way to serialize a live workflow run into something a fresh clone can
replay.

**Decision:**
1. Ship one real, generic, working kit —
   `agent-with-memory-and-knowledge` — that demonstrates the product
   *shape* (agent + memory + knowledge + workflow composed together)
   without claiming to be any specific named product. Building a
   Tryvanta-shaped (etc.) kit is left as real, documented future work
   gated on an actual product decision, not guessed at here.
2. A `StarterKit` composes what's genuinely portable
   (`AgentBlueprint`, written as JSON) with **generated source code**
   (`main.py`, via `template-factory`'s `Template`/`instantiate()`)
   rather than attempting to serialize live objects. The generated
   `main.py` is real, tested, runnable Python that calls this
   platform's actual public APIs (`ChiefDomainAgent`, `KnowledgeBase`,
   `build_memory_policy`, `WorkflowEngine`) — a clone is a working
   program, not a frozen snapshot.

**Alternatives considered:**
1. *Guess at one named product's shape to satisfy the literal ROADMAP
   bullet* — rejected: would fabricate business requirements (target
   users, specific knowledge domain, specific agent mission) nobody has
   actually specified, directly against the Master Constitution's "no
   business logic in the platform" principle.
2. *Pickle/serialize a `WorkflowSpec` instance into the kit* —
   rejected: step handlers are closures over specific objects (a
   specific `KnowledgeBase`, a specific `ChiefDomainAgent`); pickling
   them either fails outright or produces something that only works by
   accident in the exact same process, which is not what "clone-and-go"
   means.

**Consequences:** `factories/starter-kit-factory` depends on `core/`,
`agent-factory`, and `template-factory`. ROADMAP.md Phase 10's "first
real product" bullet is explicitly not delivered as originally phrased;
this ADR is the record of why, and what shipped instead satisfies the
framework's actual responsibility (composing platform building blocks
into a working starting point) without overstepping into product
decisions that aren't this platform's to make.

---

## ADR-0017: `evaluation-factory` closes ADR-0014's seam as a bridge into `agent-factory`'s `QualityGate`, not the reverse

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ADR-0014 (Phase 8) deliberately left `prompt-factory`'s
scoring seam (`EvalCase`/`EvalReport`/`Scorer`) to be *extended* by
Phase 11's evaluation-factory rather than depended upon by it, to avoid
a forward dependency on a not-yet-built framework. Separately,
`agent-factory` (Phase 3, locked) already has its own minimal
self-evaluation primitive, `QualityGate.check(AgentResult) -> bool`,
used by the reasoning loop directly. The question at Phase 11: does the
Evaluation Framework become a dependency `agent-factory` reaches into
(reopening Phase 3), or a consumer of `agent-factory`'s existing public
type?

**Decision:** Reuse the dependency-direction discipline established by
every later framework since `mcp-factory` (ADR-0011): `avishkar_evaluation`
imports `avishkar_prompt`'s `EvalCase`/`EvalReport`/`RegressionResult`/
`Scorer` verbatim (closing ADR-0014's seam exactly as promised, no
parallel type), and `agent_bridge.make_quality_gate()` **produces** a
real `avishkar_agent.QualityGate` from an `EvalSuite` — a pure consumer
of `agent-factory`'s already-public type. `agent-factory`'s locked
source is untouched; a Chief Domain Agent opts into evaluation-framework
-backed gating by passing a gate `make_quality_gate()` built into its
own `quality_gates=` constructor argument, which already existed for
exactly this purpose since Phase 3.

**Alternatives considered:**
1. *Have `agent-factory` import `evaluation-factory` and gain a new
   built-in gate type* — rejected: reopens and re-tests a locked
   framework (Phase 3) for a capability it already exposed a seam for
   (`quality_gates: Sequence[QualityGate]`), identical reasoning to
   ADR-0011 §3's rejection of modifying `agent-factory`'s `ToolRegistry`.
2. *Define a separate `EvaluationGate` type instead of producing a real
   `QualityGate`* — rejected: would require `agent-factory` to accept a
   second gate type it doesn't know about, defeating the entire point
   of reusing the existing seam.

**Consequences:** `factories/evaluation-factory` depends on `core/`,
`prompt-factory`, `agent-factory`, and `workflow-factory` — evaluation
is meant to be usable everywhere, so a broad (but one-directional, no
locked framework touched) dependency footprint is expected and correct.

---

## ADR-0018: `security-factory` keeps automated scanning and human-judgment review explicitly separate; guardrails are a bridge into `agent-factory`, not a new gate type

**Status:** Accepted · **Date:** 2026-08-09

**Context:** STANDARDS.md §6 and this framework's own pre-Phase-12
README describe two different kinds of check under one "checklist"
label: things a program can verify (no committed secret matching a
known pattern) and things that genuinely require a human's judgment
call (is rate limiting *appropriately* configured for this specific
external system?). Presenting both as if `run_checklist()` verified
them equally would overstate what this framework actually does —
a real risk for a security tool specifically, since a false sense of
automated coverage is worse than an honest gap.

**Decision:** Keep the two mechanisms explicit and separately named:
`scan_for_secrets`/`scan_repository_for_secrets` are real, automated,
regex-based detection — run for real against this repository in this
phase's own example (CONTRACT.md §1). `run_checklist()` is a
structured self-assessment for everything else — it validates that
every item has an answer (`MissingAnswerError`/
`UnknownChecklistItemError`), but cannot verify the answer is honest,
and its own docstrings/README say so. Separately, guardrail bridges
(`make_secret_scanning_guardrail`, `make_rate_limit_guardrail`,
`make_input_validation_guardrail`) produce real
`avishkar_agent.Guardrail` instances — the same "later framework
consumes an earlier framework's already-public type" discipline every
framework since `mcp-factory` has followed (ADR-0011) — rather than
inventing a parallel `SecurityCheck` type `agent-factory` would need
to learn about.

**Alternatives considered:**
1. *Have `run_checklist()` claim full automated verification* —
   rejected outright: a security framework overstating its own
   coverage is a worse failure mode than an honest, narrower scope.
2. *Store the full matched secret text on `SecretMatch` for
   debugging* — rejected: a tool whose own output leaks the secrets it
   finds defeats its purpose; `.preview` (redacted) is the only form
   ever stored, per CONTRACT.md §1.

**Consequences:** `factories/security-factory` depends on `core/` and
`agent-factory` (guardrail bridge only). The retroactive review this
phase's example ran found zero real secrets in the repository — the
only pattern matches are the example's own well-known-fake AWS
placeholder and this framework's deliberately-fake test fixtures,
both expected and explained in the example's own output.

---

## ADR-0019: Execution Mode complete — Phases 5–15 closed

**Status:** Accepted · **Date:** 2026-08-09

**Context:** ADR-0012 entered Execution Mode for Phases 5–15,
authorizing continuous, unattended execution with a pause only for a
decision genuinely requiring approval. That authorization has now been
exercised to completion: every phase in the locked build order
(ROADMAP.md) has shipped, been tested, been documented, and been
committed. This ADR is the closing record, not a new decision — the
same discipline as every phase before it (real design, working code, a
contract where a new framework was introduced, passing tests, a
runnable example, honest documentation, ROADMAP/CHANGELOG updates, its
own commit) held for all eleven phases this mode covered.

**What shipped under Execution Mode (Phases 5–15):**
- **Frameworks (8):** Memory, Knowledge, Workflow, Prompt, Template,
  Starter Kit, Evaluation, Security — joining the four built before
  Execution Mode (Core, Router, Agent, Universal Integration/MCP) for
  12 of 16 originally-scoped frameworks built; the remaining 4
  (`langgraph-factory`, `n8n-factory`, `project-factory`,
  `documentation-factory`) remain deliberately deferred per ADR-0009,
  each requiring its own future ADR to schedule — not silently
  dropped.
- **Chief Domain Agents (10):** Medical & Healthcare, Legal &
  Compliance, Startup Business & Product, Education & Knowledge,
  Research & Intelligence, Finance & Economics, Government & Public
  Policy, Human Development & Psychology, Creative & Media, and
  Orchestrator — completing all 11 seats in ADR-0007's locked roster
  (Software & AI Engineering was built in Phase 3, before Execution
  Mode).
- **Knowledge Library (Phase 14):** one concrete, product-facing
  artifact in each of `knowledge/`, `workflows/`, and `templates/` —
  the shelves that previously held only a README pointing at their
  owning factory.
- **Final Integration (Phase 15):** a real, runnable script and
  cross-cutting doc (`docs/final-integration.md`) proving Core Engine,
  AI Router, Universal Integration, Agent Framework, Memory, Knowledge,
  Workflow, Evaluation, and Security compose together in one pass.

**Decisions recorded along the way (ADR-0013 through ADR-0018):**
`workflow-factory`'s plain-callable step engine (not un-deferring
`langgraph-factory`); `prompt-factory`'s self-contained scoring seam
(not blocking on `evaluation-factory`); `template-factory` wrapping
`PromptVersion` directly; `starter-kit-factory` shipping one generic
kit rather than guessing at a named product's requirements;
`evaluation-factory` bridging into `agent-factory`'s existing
`QualityGate` rather than the reverse; `security-factory` keeping
automated scanning and human-judgment review explicitly separate. Every
one of these followed the same dependency-direction discipline
ADR-0011 established: a later framework consumes an earlier one's
already-public types; a locked framework's source is never reopened.

**Final metrics:** 542 tests passing platform-wide (382 across 16
factories/frameworks, 9 across Phase 14's three Knowledge Library
modules, 151 across all 11 Chief Domain Agents), zero known
regressions, one real bug found and fixed by actually running an
example in nearly every phase (per this repository's "run it, don't
just write it" discipline, unbroken since Phase 3).

**Alternatives considered:** None — this ADR records completion of an
already-authorized mode, not a new choice point.

**Consequences:** Execution Mode (ADR-0012) is closed. Future work
(un-deferring `langgraph-factory`/`n8n-factory`/`project-factory`/
`documentation-factory`; a twelfth Chief Domain Agent; real product
integration via a named starter kit) each requires its own ADR before
work begins, per the standing discipline this repository has followed
since ADR-0001 — Execution Mode's relaxed pacing does not carry
forward as a default; it was scoped to Phases 5–15 explicitly.

---

## ADR-0020: Layla is a new top-level platform capability (`layla/`), not a Chief Domain Agent, not a factory — composed entirely from existing contracts

**Status:** Accepted · **Date:** 2026-08-09

**Context:** Phase 16's directive ("Codename: LAYLA") specifies a
"Personal Executive Intelligence layer" sitting architecturally above
Router/Memory/Knowledge/Scheduler and above the Agent/Tool/MCP
ecosystem — explicitly *not* another Chief Domain Agent, *not* a
system prompt, *not* an orchestrator in the ADR-0007 sense. Nothing in
ARCHITECTURE.md's existing two categories (factories that generate
output, and library shelves that hold that output) fits: Layla is not
generated by a factory (there is exactly one Layla architecture,
parameterized by config, not a class of interchangeable generated
artifacts the way agents/prompts/templates are), and it is not a shelf
of factory output. The directive itself frames Layla as part of
**Avishkar OS** (the platform), not a specific product — "Layla is
Avishkar OS's Personal Executive Intelligence layer" — which settles
the one genuine platform-vs-product ambiguity here: CLAUDE.md's "no
business logic in the platform" rule is not violated because Layla
contains no product-specific business logic itself, only the
composition/orchestration substrate a product-facing assistant would
be configured from (the same relationship `agent-factory` has to a
specific Chief Domain Agent's blueprint).

**Decision:**
1. **New top-level directory `layla/`**, structured exactly like
   `core/`/`router/` (a singular platform-wide capability, not factory
   output): `CONTRACT.md`, `schemas/`, `python/avishkar_layla/`,
   `examples/`, `tests/`. Documented to the Framework template
   (STANDARDS.md §2.2) — "platform-wide capability" is explicitly one
   of that template's two intended uses per its own heading.
2. **Zero duplicated systems.** Every capability domain the directive
   lists maps to an existing framework's public contract, consumed as
   a client, never reimplemented:
   - Delegation wraps `avishkar_agent.Orchestrator` (already built,
     Phase 3) via the real `agents/orchestrator` package's
     `build_executive_orchestrator()` — Layla does not get its own
     agent-dispatch mechanism.
   - Memory wraps a real `MemoryPolicy` (`memory-factory`, Phase 5) —
     Layla's "what may/must-not be stored, retention, confidence,
     provenance, importance" policy is a layer of metadata *around*
     `remember()`/`recall()`, not a second memory system.
   - Tool/MCP access reuses `avishkar_integration`'s
     `UniversalToolRegistry`/`ToolRuntime`/`ProtocolAdapter` (Phase 4)
     directly — a communication channel is *implemented as* a
     `ProtocolAdapter`, not a parallel "channel" abstraction.
   - Approval reuses `avishkar_agent.ApprovalGate` for the actual gate
     mechanism (the same reuse `mcp-factory` already established,
     ADR-0011 §7) — Layla adds a *risk-classification* layer
     (LOW/MEDIUM/HIGH → which actions need a gate at all), which does
     not exist anywhere else in this platform and is genuinely new.
   - Scheduling/events reuse `avishkar_core.EventBus` (Phase 1) for
     in-process delivery; a new `Scheduler` component is genuinely new
     (nothing in Core Engine does time-based dispatch) but is built as
     a small, real, deterministic, injectable-clock component — the
     same DI discipline every timing-sensitive component in this
     repository already follows (`security-factory`'s rate limiter,
     `mcp-factory`'s retry backoff).
   - Evaluation/Security wire in `evaluation-factory`'s
     `make_quality_gate()` and `security-factory`'s guardrail bridges
     directly, the same pattern every Phase 13 Chief Domain Agent uses.
3. **Genuinely new components** (none of the above cover them):
   `StateMachine` (explicit lifecycle per the directive's Part V), risk
   classification + `ApprovalManager`, `Planner`/capability-matching
   for cross-agent plans, executive result synthesis/conflict
   detection, a durable `SessionManager` (restart-safe task state,
   built on a real `MemoryPolicy` backend — reuse, not a new
   persistence layer), and the `ExecutiveRuntime` event loop
   composing all of the above.

**Alternatives considered:**
1. *Make Layla the 12th Chief Domain Agent* — rejected: ADR-0007 locks
   the roster at 11 and requires its own ADR to grow; more
   fundamentally, Layla's shape (coordinates across agents, holds
   durable cross-session state, schedules future work) does not fit
   `ChiefDomainAgent`'s reasoning-loop-over-one-domain shape at all —
   forcing it in would be exactly the "parallel architecture because
   it's easier" Part I forbids.
2. *Put Layla under `factories/` as `layla-factory`* — rejected: there
   is nothing for it to generate; a factory produces multiple
   instances of something (agents, prompts, templates), and there is
   one Layla architecture, not a class of them.
3. *Build a new memory/scheduling/approval system from scratch for
   Layla specifically* — rejected outright per Part I's explicit
   instruction; every capability domain above was checked against the
   existing contract first.

**Consequences:** `layla/` depends on `core/`, `router/`,
`factories/agent-factory` (+ `agents/orchestrator` as a concrete
consumer), `factories/mcp-factory`, `factories/memory-factory`,
`factories/knowledge-factory`, `factories/workflow-factory`,
`factories/evaluation-factory`, `factories/security-factory` — by far
the widest dependency footprint of anything in this repository, which
is expected and correct for the outermost composition layer. No
existing framework's locked source is modified to build it.

---

## ADR-0021: Layla identity/authentication is a minimal, additive `Principal`/`Session`/`Role`/`Permission` model — not an enterprise IAM system, not a breaking change

**Status:** Accepted · **Date:** 2026-08-11

**Context:** The Phase 16 forensic audit (SEC-3, MEDIUM) found that
**no authentication/authorization model exists anywhere in this
platform** — any caller with code-level access to a `ChiefDomainAgent`
or `ExecutiveRuntime` can act as any "user," and nothing prevents an
autonomous agent from granting itself broader authority than it was
invoked with. Priority 17.1 of the Phase 17 directive asks for a real
identity boundary integrated with Layla's existing
`IntentInterpreter`/`risk.classify_risk`/`CapabilityResolver`/
`ApprovalManager`/`DelegationEngine`/`AuditLogger` — explicitly
**not** "enterprise identity infrastructure this platform doesn't
need," and explicitly required to keep all 149 (119 Phase 16 + 30
Phase 17.1) Layla tests — and the platform's other 542 — passing
unmodified.

**Decision:**
1. **A minimal, real, in-process model** (`identity.py`): `Principal`
   (id, kind ∈ {user, agent, system}), `Role` (a fixed six-permission
   vocabulary, optionally scoped to specific capabilities), `Session`
   (issued, expiring, revocable). No JWT/OAuth/OIDC machinery — those
   integrate *behind* `AuthorizationManager.issue_session()` later
   (a real deployment would replace/wrap session issuance with a real
   IdP; nothing else in this design needs to change for that).
2. **A fixed permission vocabulary, not open-ended RBAC strings** —
   `PERM_COMMAND`/`PERM_INVOKE_AGENT`/`PERM_INVOKE_AGENT_WRITE`/
   `PERM_INVOKE_AGENT_HIGH_RISK`/`PERM_APPROVE`/`PERM_TOOL_INVOKE`.
   Adding a permission is a deliberate code change to this list, not a
   runtime string any caller can invent to bypass enforcement.
3. **Every integration point is additive.** `ExecutiveRuntime`,
   `ApprovalManager`, `DelegationEngine`, `AuditLogger` all accept
   `authorization`/`session_id`/`principal_id`/`requested_by` as
   **optional** parameters defaulting to `None`. Omitted: behavior is
   byte-for-byte Phase 16 (verified — all 119 original Layla tests
   pass unmodified against the Phase 17.1 code). Supplied: full
   enforcement activates. This is the same "extend, don't break"
   discipline `approval_gate=`/`scheduler=`/`event_bus=` already
   established as optional `ExecutiveRuntime` constructor arguments in
   Phase 16 — Priority 17.1 follows the existing pattern rather than
   inventing a new one.
4. **Structural, not conventional, anti-escalation.**
   `AuthorizationManager.issue_session()` *refuses* to issue a session
   granting `PERM_INVOKE_AGENT_HIGH_RISK` or `PERM_APPROVE` to a
   `kind="agent"` `Principal` — checked against the role's actual
   permission set at issuance time, regardless of the role's name.
   Even a maliciously-named custom role (`register_role(Role("sneaky",
   (PERM_APPROVE,)))`) cannot be granted to an agent-kind principal —
   proven by test, not merely documented (Priority 17.1 SS5's explicit
   requirement).
5. **Least-privilege capability enforcement composes by union.**
   `Role.allowed_capabilities` (`None` = unrestricted) lets a
   deployment scope a session to specific Chief Domain Agents;
   `ExecutiveRuntime` checks every `PlanStep.required_capability`
   against it *before* delegating, blocking the whole plan (not
   silently dropping the disallowed step) if any step fails the check.
6. **Self-approval is always denied**, independent of role —
   `ApprovalRequest.requested_by` is compared against the approving
   session's `principal.id` in `ApprovalManager.grant()`, even if that
   principal separately holds `PERM_APPROVE` via another role.

**Alternatives considered:**
1. *Integrate a real OAuth/OIDC library now* — rejected per the
   directive's own explicit instruction ("do not invent enterprise
   identity infrastructure the platform does not currently need") and
   STANDARDS.md's YAGNI principle: no deployment exists yet to
   configure a real IdP against.
2. *Make `session_id` a required parameter everywhere* — rejected:
   would break all 119 Phase 16 tests and every existing example
   script, for a security property better achieved by making
   enforcement opt-in-and-total (once `authorization=` is supplied,
   nothing bypasses it) rather than mandatory-and-disruptive.
3. *A single flat permission list with no `Role` grouping* — rejected:
   roles are the natural unit an operator actually assigns ("give
   Alice the operator role"), and `allowed_capabilities` needed a home
   more specific than a bare permission string.

**Consequences:** `layla/python/avishkar_layla/auth.py` and
`identity.py` depend on nothing outside `layla/` itself and stdlib —
the identity model doesn't reach into `core/`/`agent-factory`/etc.,
keeping it a pure addition. A real identity provider integration
(API keys, device auth, a real OIDC flow) is real future work, tracked
in `layla/README.md`'s Priority 17.1 section, not built speculatively
here. `docs/production-readiness.md` (Priority 17's final deliverable)
must state plainly that this is a foundation, not a hardened,
externally-audited auth system.

## ADR-0022: Idempotency is a real `ExecutionTracker` owned by `DelegationEngine`, keyed per-step, persisted through `LaylaMemoryPolicy` — not a second workflow engine, not a change to `mcp-factory`

**Status:** Accepted · **Date:** 2026-08-11

**Context:** Priority 17.2 of the Phase 17 directive requires that
Layla distinguish READ from WRITE/HIGH-RISK operations, assign every
externally consequential operation an idempotency key, persist
execution state so retries cannot duplicate a real-world side effect,
and handle uncertain outcomes (e.g. a timeout on a WRITE after the
provider may have already accepted it) safely rather than blindly
resending. The Phase 16 audit had already flagged (SEC-1/RE-2) that
no live external call had ever been exercised and that
`DelegationEngine`'s retry loop had no concept of "this attempt might
have already had a real effect" — every retry today is unconditionally
safe only because every test target is a mock.

**Decision:**
1. **A genuinely separate classifier from risk.** `execution.
   classify_operation()` (READ/WRITE/HIGH_RISK) is not `risk.
   classify_risk()` (LOW/MEDIUM/HIGH) wearing a new name — risk asks
   "how much harm can this cause" (approval-worthiness); operation kind
   asks "does retrying this risk duplicating a real effect"
   (idempotency-worthiness). A LOW-risk action ("send a routine status
   email") can still be a WRITE that must never be silently retried.
   Fail-closed default: unrecognized text classifies `WRITE`, never
   `READ`.
2. **One storage mechanism, not a second one.** `ExecutionTracker`
   persists `ExecutionRecord`s through the *same* `LaylaMemoryPolicy`
   every other Layla component already uses — `kind="long_term"`
   (already the locked backend's fourth fixed kind, per ADR-0020's own
   discovery), keys namespaced `execution:{idempotency_key}`. No new
   backend, no new dependency.
3. **`DelegationEngine` owns idempotency, not a new engine.**
   `execution_tracker` is an *optional* `DelegationEngine`/
   `ExecutiveRuntime` constructor parameter — the identical additive
   pattern ADR-0021 established for `authorization`. Omitted: behavior
   is byte-for-byte Phase 16/17.1 (all 149 prior tests pass
   unmodified). Supplied: every `delegate()` call is keyed
   `{task_id}:{plan_step.id}`, checked before the retry loop runs, and
   the record is transitioned to a terminal (or `UNKNOWN`) state after
   it finishes. This directly satisfies the directive's explicit "do
   NOT create a separate workflow engine — reuse existing Layla runtime
   and frameworks" instruction (stated for Priority 17.3, but the same
   principle governs 17.2's own integration point).
4. **`UNKNOWN` is a real, non-terminal state, not folded into
   `FAILED`.** A timeout on a non-READ operation cannot be assumed
   safe to retry (the call may have landed) nor assumed failed (it may
   not have) — it is recorded `UNKNOWN` and `TERMINAL_EXECUTION_STATES`
   deliberately excludes it. The only way past it is
   `ExecutionTracker.resolve_unknown()`, an explicit, human/caller-
   driven call — never an automatic retry.
5. **Fail-closed on any unresolved non-terminal state, not just
   `UNKNOWN`.** A record still `AUTHORIZED`/`APPROVED`/`EXECUTING` —
   which happens identically whether a second call arrived
   concurrently or a first attempt crashed mid-flight, since
   `DelegationEngine` cannot tell those two situations apart from the
   record alone — refuses a non-READ retry rather than guessing which
   case it is. This is the same conservative default Priority 17.3's
   crash-recovery scenario needs, built once here rather than twice.
6. **`mcp-factory` is not touched.** `ExecutionTracker` guards the one
   seam Layla actually owns — `DelegationEngine.delegate()`, i.e. the
   call *into* a `ChiefDomainAgent`. A delegated agent's own direct
   `ToolRuntime.invoke()` calls remain outside this tracker's
   visibility; threading an idempotency key through
   `ToolContract`/`ProtocolAdapter` itself would be a `mcp-factory`
   (Phase 4, locked) change, out of scope here per this repository's
   "later frameworks wrap, never modify earlier locked frameworks"
   discipline (already established for `channels/email_adapter.py` in
   Phase 16).
7. **`IdempotencyConflictError` guards key reuse, not just retries.**
   `ExecutionTracker.begin()` compares the new call's `description`
   against an existing record's; a mismatch (the same key reused for a
   genuinely different operation — a collision bug, not a retry) raises
   rather than silently returning the wrong cached result.

**Alternatives considered:**
1. *A generic distributed-transaction/saga library* — rejected: no
   deployment need for cross-service transactional guarantees exists
   yet; `ExecutionTracker` solves the actual stated problem (don't
   duplicate a side effect on retry) without that machinery.
2. *Fold operation classification into `risk.classify_risk`* — rejected:
   conflates two independent questions (harm vs. duplication-safety);
   a LOW-risk WRITE would otherwise never get idempotency protection.
3. *Treat a timeout as `FAILED` and let the existing retry loop handle
   it* — rejected: this is exactly the directive's named failure mode
   ("do NOT blindly resend") — a `FAILED` status implies "safe to
   retry," which a timeout does not guarantee for a WRITE/HIGH_RISK
   step.
4. *Store execution state as a new `episodic` memory kind, matching
   `AuditLogger`* — rejected: `long_term` already fits (durable,
   queried by key, not a stream), and reusing it — as `SessionManager`
   and `ProjectStore` already do — avoids adding a de facto fifth kind
   the locked backends were never designed for.

**Consequences:** `layla/python/avishkar_layla/execution.py` depends
only on `.memory_policy` and `.errors` — no new external dependency.
`DelegationEngine`/`ExecutiveRuntime` gain one optional parameter each;
zero regressions verified (149 → 170 tests, all passing, the original
149 unmodified). What remains explicitly unbuilt: idempotency
awareness inside a delegated agent's own direct tool calls (a
`mcp-factory` change, tracked as future work in `layla/README.md`);
automatic resolution of `UNKNOWN` outcomes (deliberately manual).
`docs/production-readiness.md` must state that idempotency protection
covers the Layla→Agent delegation seam only, not every possible
external side effect an agent's own tools might perform.

## ADR-0023: Resume-in-place is two entry points around one shared, state-guarded pipeline — not a second workflow engine, built on Priority 17.2's ExecutionTracker rather than duplicating it

**Status:** Accepted · **Date:** 2026-08-11

**Context:** Priority 17.3 of the Phase 17 directive requires Layla to
survive interruption -- its own named example: a 50-company research
task that crashes after company 17 must resume from company 18, not
restart blindly. It explicitly forbids building a separate workflow
engine, requiring reuse of "the existing Layla runtime and frameworks."
`SessionManager` (Phase 16) already persisted a `LaylaTask`'s `state`
and `history`, and `ExecutionTracker` (Priority 17.2, ADR-0022) already
persisted per-delegation-step outcomes keyed `{task_id}:{step.id}` --
but nothing tied them together into an actual resumable pipeline:
`ExecutiveRuntime.handle_event()` was a single monolithic method that
only ever ran a task from `RECEIVED`, and the `Plan` itself (the steps
a resumed task would need to continue) was never persisted at all.

**Decision:**
1. **One pipeline, two entry points, not two pipelines.**
   `handle_event()` (new task, starts at `RECEIVED`) and `resume()`
   (existing task, starts wherever it was last checkpointed) both call
   a single private `_advance(task, session_id=)`. Every stage inside
   it is guarded by `if task.state == X:` rather than assumed to run in
   sequence from the top -- transitioning `task.state` inside a guard is
   what makes the *next* guard's condition become true, so a fresh task
   runs straight through exactly as Phase 16 did, and a reloaded task
   skips directly to its first unfinished stage. This is the entire
   mechanism; there is no separate scheduler, queue, or state-transition
   table beyond the one `StateMachine` already enforces.
2. **The Plan itself becomes persisted state, not just its id.**
   `LaylaTask.plan: Optional[Plan]` (additive field) and
   `SessionManager` serializes it. Reconstructing a plan via `Planner`
   again on resume would be a *different* operation (possibly different
   capabilities inferred, a new `Plan.id`) than continuing the one
   already committed to; a resumed task must continue the *same* plan.
3. **Idempotent step-skipping is Priority 17.2's `ExecutionTracker`,
   reused, not reimplemented.** A resumed task at `EXECUTING` re-runs
   the *entire* delegation loop over `plan.steps` from the top --
   deliberately not "resume from step N," which would require Layla to
   track per-step progress a second time. Instead, each
   `DelegationEngine.delegate()` call independently checks
   `ExecutionTracker` (already there, Priority 17.2): an already-
   `COMPLETED` step returns its cached result without invoking the
   orchestrator again. This is the actual mechanism satisfying the
   directive's "resume from company 18, not from scratch" example --
   built by composing 17.2 and 17.3, not by inventing a second
   checkpoint format.
4. **Three durable checkpoints, chosen by consequence, not by state
   count.** `self._session.save(task)` fires right after a `Plan` is
   created (state `PLANNING`), right after an `ApprovalRequest` is
   created (state `APPROVAL_PENDING`), and right before delegation
   starts (state `EXECUTING`) -- each the last point before something
   either expensive (re-planning) or externally consequential
   (delegation, an approval decision) happens. States before the first
   checkpoint are pure, synchronous, side-effect-free computation with
   nothing persisted mid-way; a crash that early means the request was
   never durably received, and resubmitting via `handle_event()` is the
   correct recovery, not finer-grained checkpointing of code that does
   no I/O.
5. **`APPROVAL_PENDING` becomes a real, resumable, persisted state.**
   Phase 16/17.1 collapsed an ungated pending approval straight to
   `REQUIRES_HUMAN` within the same synchronous call, because nothing
   could ever come back to check it again. Resume-in-place needs a task
   to actually be resumable *from* `APPROVAL_PENDING`, so
   `ExecutiveRuntime` now leaves it there and only collapses to
   `REQUIRES_HUMAN` once the request is actually denied/expired. This
   required `ApprovalManager` to gain an optional `memory=` parameter
   (the same additive pattern as everywhere else in Priority 17) so the
   pending decision itself survives a restart, not just the task
   record referencing it.
6. **A real, previously-latent bug, found by actually running the
   resume scenario end-to-end, fixed rather than worked around.**
   `DelegationEngine`'s own `approval_manager=` parameter re-checks
   approval per-step independently of `ExecutiveRuntime`'s task-level
   decision. In Phase 16/17.1 this was dormant (an ungated pending
   task-level approval never reached `DELEGATING` in the first place).
   Once `resume()` could legitimately carry a task-level-granted
   approval through to `DELEGATING`, the orphaned per-step
   `ApprovalRequest` -- created fresh inside `delegate()`, its id never
   surfaced anywhere a human could grant it -- wrongly denied the step.
   Fixed by no longer passing `approval_manager=` into the
   `DelegationEngine` `ExecutiveRuntime` constructs internally, since
   `ExecutiveRuntime` already fully gates the decision before
   `EXECUTING` is ever reached; `DelegationEngine` keeps the parameter
   for direct, standalone use (`test_delegation.py`).

**Alternatives considered:**
1. *A separate `WorkflowEngine`/`ResumableTask` abstraction* -- rejected
   per the directive's own explicit instruction and because nothing
   about resuming needs new machinery: the existing `StateMachine`,
   `Planner`, `ApprovalManager`, `DelegationEngine`, and `SessionManager`
   already cover every piece; the only genuine gaps were "the plan isn't
   persisted" and "the pipeline can't be entered mid-way," both closed
   additively.
2. *Track per-step delegation progress as a new field on `LaylaTask`
   (e.g. `completed_step_ids`)* -- rejected: this would duplicate
   `ExecutionTracker`'s own per-step state in a second location that
   could drift out of sync with it; re-running the full loop and
   letting `ExecutionTracker` skip completed steps keeps exactly one
   source of truth per step.
3. *Auto-collapse `APPROVAL_PENDING` to `REQUIRES_HUMAN` as before, and
   have `resume()` treat `REQUIRES_HUMAN` as resumable too* -- rejected:
   `REQUIRES_HUMAN` is deliberately a broader bucket (capability denied,
   plan failed, conflict detected, approval denied/expired) where
   "resume automatically" is not always correct; keeping
   `APPROVAL_PENDING` genuinely alive lets `resume()` treat exactly one
   well-defined case (an undecided approval) as safely re-checkable,
   while `REQUIRES_HUMAN` stays a true dead end requiring an explicit
   human decision first.

**Consequences:** `types.py` gains two additive `LaylaTask` fields
(`plan`, `pending_approval_id`); `session.py` serializes both;
`approval.py` gains an optional `memory=` parameter; `runtime.py`'s
`handle_event()` body is restructured into the shared, state-guarded
`_advance()` plus the new `resume()` entry point; `DelegationEngine`'s
`ExecutiveRuntime` no longer passes it an `approval_manager=`. Zero
regressions verified (170 → 178 tests, all passing, the original 170
unmodified). What remains explicitly unbuilt: sub-step-granularity
resume for `UNDERSTANDING`/`CONTEXT_LOADING`/`PLANNING` (unnecessary --
those phases do no I/O); automatic re-driving of `REQUIRES_HUMAN` tasks
once a human acts (a deployment's own code calls `resume()` after the
decision); coordination if multiple processes call `resume()` on the
same task concurrently (Priority 17.4's concern, not this one's).
`docs/production-readiness.md` must state that resume-in-place has been
verified via simulated crashes (fresh objects against the same on-disk
store), not via an actual killed OS process.

## ADR-0024: Concurrency hardening is narrow, additive, per-component locks — sized to the actual races found by audit, not a blanket rewrite; a bounded, justified exception to core/memory-factory/mcp-factory's locked status

**Status:** Accepted · **Date:** 2026-08-11

**Context:** Priority 17.4 of the Phase 17 directive requires auditing
`EventBus`, `Scheduler`, Layla's `ExecutiveRuntime`, `DelegationEngine`,
the Agent Framework, Memory, and `ToolRuntime` for shared mutable state
and race conditions, defining concurrency/ordering guarantees, and
adding locking/atomicity "ONLY where justified." The Phase 16 forensic
audit had already flagged `EventBus._subscribers` and `Scheduler._heap`
as mutated without synchronization but never verified whether that
mattered in practice. Every test in this platform through Phase 17.3
runs single-threaded; nothing had ever actually exercised these
components under real concurrent access.

**Decision:**
1. **Audit first, by reading the actual mutation patterns, not by
   assumption.** Concretely walked every named component's source for
   read-modify-write sequences on shared mutable state. Found real,
   confirmed races in: `ExecutionTracker.begin()` (check-then-act
   idempotency-record creation -- the exact property idempotency exists
   to guarantee, undermined under concurrency), `ApprovalManager.grant()
   /deny()` (read-mutate-write on a shared `ApprovalRequest`),
   `SessionManager.save()` and `AuditLogger.record()` (both a shared
   index's read-modify-write), `Scheduler` (heap/dict mutation across
   `schedule_once()`/`cancel()`/`tick()`), `EventBus`
   (`_subscribers`/`_next_id`), `FileMemoryPolicy` (a *lost-update* bug:
   whole-file load-mutate-save means two concurrent `remember()` calls
   for different keys in the same kind can silently discard one
   entirely), `SQLiteMemoryPolicy` (unusable cross-thread at all by
   default -- `check_same_thread=True` -- not a subtle race but an
   outright `ProgrammingError`), and `MetricsCollector.record()`
   (counter increments). Found *no* race in `Orchestrator` (its
   `_agents` dict is populated once at construction, read-only
   afterward) or `InMemoryMemoryPolicy` (each operation is a single
   dict op, atomic under the GIL) -- these were left untouched, because
   nothing was actually wrong with them.
2. **One lock per component instance, not per key/task/request id.**
   Every fix above uses a single `threading.Lock`/`RLock` scoped to the
   owning object, guarding only its own read-modify-write sequences.
   Rejected per-key locking (see Alternatives) as unjustified complexity
   for this platform's actual scale -- these are fast, local,
   in-memory-or-disk operations, never a locked section spanning
   network I/O.
3. **Locks never wrap the actual work, only the bookkeeping.**
   `ExecutionTracker.begin()`'s lock covers get-or-create, released
   before `DelegationEngine` calls the orchestrator; `Scheduler.tick()`
   pops/reschedules a due job under the lock, then calls its callback
   *outside* it; `EventBus.publish()` snapshots matching handlers under
   the lock, then invokes them outside it. Holding a lock across
   arbitrary external work (an orchestrator call, a user callback) would
   either serialize unrelated concurrent operations for no reason, or
   deadlock outright if that work calls back into the locked component
   (a callback that reschedules itself; an audit subscriber that
   publishes another event).
4. **`begin()`'s return gained a `claimed_this_call` marker, not a
   changed return type.** The real race -- two threads observing the
   same freshly-created `EXEC_REQUESTED` record and both proceeding --
   needed a way to distinguish "I created this" from "I found one
   already there," but both cases have identical `.status`. Rather than
   changing `begin()`'s signature to a tuple (breaking every existing
   call site across three already-committed priorities' worth of
   tests), a non-persisted dynamic attribute on the returned
   `ExecutionRecord` carries the distinction -- backward compatible
   with every caller that only reads `.status`.
   `_CLAIMED_NON_TERMINAL_STATES` (delegation.py) was extended to
   include `EXEC_REQUESTED` alongside `AUTHORIZED`/`APPROVED`/
   `EXECUTING`/`UNKNOWN`, using this marker to avoid the fix rejecting
   the legitimate creator's own first call.
5. **`ExecutiveRuntime` gets a per-task-id lock spanning the *entire*
   `_advance()` call, including the reload inside `resume()`.** This is
   the one lock in this pass that is deliberately coarser than "just
   the bookkeeping": two `resume()` calls racing the same task id must
   not each load their own stale snapshot before either one's work
   runs, or the second (once unblocked) would redo the first's already-
   completed delegation. Loading *inside* the lock, not before it, is
   what closes this.
6. **A bounded, justified exception to three "locked" frameworks'
   status.** `core/` (Phase 1), `memory-factory` (Phase 5), and
   `mcp-factory` (Phase 4) are otherwise treated as closed to
   modification per this repository's own "later frameworks wrap,
   never modify earlier locked frameworks" discipline (ADR-0020 and
   throughout Layla's build). This priority is the deliberate,
   directive-authorized exception: the Phase 17 directive explicitly
   names EventBus, Memory, and ToolRuntime as audit/harden targets, and
   every change is additive (a lock that changes nothing about
   single-threaded behavior) -- verified concretely by re-running each
   framework's own full pre-existing test suite unmodified (core: 47/47,
   memory-factory: 24/24, mcp-factory: 70/70, all still passing).

**Alternatives considered:**
1. *Per-key/per-task-id locks everywhere (not just `ExecutiveRuntime`)*
   -- rejected: needs its own lock-lifecycle management (when is a
   per-key lock safe to forget without leaking memory indefinitely?)
   for a benefit that only matters at far higher contention than this
   platform's current scale; a single coarse lock per fast, local
   component is simpler and no less correct at this scale.
2. *A single global lock across all of Layla* -- rejected: would
   serialize genuinely independent work (two different tasks, two
   different approval requests) for no correctness reason, defeating
   the entire purpose of "10 simultaneous tasks" working concurrently.
3. *Change `ExecutionTracker.begin()`'s return type to `Tuple[Record,
   bool]`* -- rejected in favor of the non-persisted attribute marker,
   specifically to avoid a breaking API change to already-committed
   Priority 17.2/17.3 test code for a distinction only `DelegationEngine`
   itself needs to make.
4. *Leave `FileMemoryPolicy`/`SQLiteMemoryPolicy`/`EventBus` alone,
   document the races as known limitations instead of fixing them* --
   rejected: `FileMemoryPolicy`'s bug is a silent, undetectable data
   loss (a written key simply vanishes), not a theoretical edge case,
   and `SQLiteMemoryPolicy` couldn't be used cross-thread *at all*
   before this fix -- both were correctness bugs the directive's own
   named audit targets, not stylistic nitpicks to defer.
5. *Real OS-level file locking (fcntl/msvcrt) for
   `FileMemoryPolicy` to also cover cross-process safety* -- rejected
   as out of scope for this pass: the confirmed, reproduced bug was
   single-process (multiple threads in one Python process), and cross-
   process coordination is explicitly called out as unbuilt in
   `docs/production-readiness.md` rather than partially/silently solved.

**Consequences:** Ten files gained a lock: `execution.py`,
`approval.py`, `session.py`, `audit.py`, `scheduler.py`, `runtime.py`
(Layla, freely modifiable), plus `core/python/avishkar_core/
event_bus.py`, `factories/memory-factory/python/avishkar_memory/
backends/{file_backend,sqlite_backend}.py`, and `factories/mcp-factory/
python/avishkar_integration/metrics.py` (the bounded, documented
exception above). 11 new tests (`test_concurrency.py`) using real
`threading.Thread`s and, where the natural race window is too narrow to
hit reliably under the GIL's scheduling, a test double that sleeps
mid-operation to widen it deterministically plus a `threading.Barrier`
to force simultaneous entry. Zero regressions across Layla (170 → 178
→ 189 tests through this priority) and the three touched external
frameworks' own full suites. What remains explicitly unbuilt:
cross-process/distributed coordination (no distributed lock, no
multi-worker-safe file locking); a deeper audit of
`UniversalToolRegistry`/rate-limit enforcement in mcp-factory beyond
`MetricsCollector`. `docs/production-readiness.md` must state plainly
that these locks provide single-process thread-safety, not
multi-process/multi-worker safety.

## ADR-0025: Controlled live integration validation is one env-gated, cost-bounded test, not a new "live mode" for Layla — built, verified to skip correctly, not fabricated as verified-live

**Status:** Accepted · **Date:** 2026-08-11

**Context:** Priority 17.5 of the Phase 17 directive, and the Phase 16
forensic audit's own headline finding (SEC-1, HIGH), both name the same
gap: every test in this platform, through 661+ tests across 16 phases,
runs offline against dependency-injected fakes. `AnthropicProvider`
(router/python/avishkar_router/providers/anthropic_provider.py)
already existed, real and complete, tested only via an injected fake
`client`. The directive explicitly forbids making Layla "fully
autonomous against real external systems" and requires: opt-in only
(default mock/offline), credentials from environment variables only,
spend safeguards, tracking of model/latency/tokens/cost/request id/
errors/retries, validation of the *full* Layla→Router→provider→
response→validation→synthesis path, no real destructive/financial/
messaging side effects, and — critically — "if credentials unavailable
... do NOT fabricate successful live validation."

**Decision:**
1. **One test file, `@unittest.skipUnless`-gated on two independent
   conditions** (`LIVE_TEST_MODE` env var AND a real
   `ANTHROPIC_API_KEY`), not a new runtime mode, config flag, or code
   path inside `ExecutiveRuntime`/`DelegationEngine` itself. Layla's
   own code has no notion of "live mode" — the gating lives entirely in
   the test, which is the correct place for something that must default
   to never running.
2. **Validates through Layla, not just through Router directly.** The
   test builds a real `ChiefDomainAgent` wired to a real `Router`+
   `AnthropicProvider`, registers it with a real `Orchestrator`, and
   drives it through `ExecutiveRuntime.handle_event()` — exercising
   `Planner`, `DelegationEngine`, `ResultValidator`, and
   `ExecutiveSynthesizer` for real, not just confirming the Router-level
   plumbing (already covered, offline, by router/python/tests).
3. **Safety by construction, not by trusting the caller.** Fixed to the
   cheapest catalog model (`claude-haiku-4-5`), `max_tokens=32`, one
   fixed trivial prompt, and an explicit assertion that the real
   reported cost stays under a hand-picked ceiling ($0.01) — the test
   fails loudly, not silently, if cost is ever higher than expected.
   The task itself is phrased read-only/LOW-risk so it never reaches
   `DelegationEngine`'s write-classified idempotency path or triggers
   an `ApprovalManager` gate — no tool/channel adapter is invoked at
   all.
4. **Closed a real, small observability gap this priority actually
   needed.** `Router.route()` already computed and logged/published
   `cost_usd`/`latency_ms`/`input_tokens`/`output_tokens` per call
   (Phase 2) — the one thing missing for the directive's explicit
   "track ... request ID" requirement was the provider's own request
   id, silently available only inside `ProviderResponse.raw` and
   discarded by the time `Router.route()` built `CompletionResponse`.
   Added `request_id: Optional[str] = None` to both dataclasses
   (additive, defaults `None`, `MockProvider` unaffected) and populated
   it in `AnthropicProvider` from the real response's `.id`. Also added
   `DelegationRecord.cost_usd: float = 0.0` (Layla's own type) so real
   spend is visible at the Layla layer without reaching into `Router.
   cost_tracker` directly.
5. **No credentials were available when this priority was built, and
   that is stated plainly, not worked around.** The skip path was
   verified (the test correctly reports `skipped`, not a fabricated
   `ok`); a real live run against the Anthropic API was not performed
   as part of this work. `docs/live-integration-guide.md` and
   `docs/production-readiness.md` say this explicitly — per the
   directive's own closing instruction, "be honest about anything that
   could not actually be verified."

**Alternatives considered:**
1. *A `LIVE_TEST_MODE` flag threaded through `ExecutiveRuntime`/
   `DelegationEngine` itself* — rejected: Layla's own runtime has no
   legitimate reason to know or care whether a test harness intends to
   spend real money; that concern belongs entirely in the test that
   constructs a real vs. fake provider, not in production code.
2. *Mock the Anthropic SDK's HTTP layer with a recorded cassette
   (VCR-style) instead of a real opt-in call* — rejected for this
   priority: a cassette replay is still not a live call and wouldn't
   satisfy the directive's explicit ask to validate against the real
   provider; it's reasonable *future* work for a faster CI-safe smoke
   test, not a substitute for this priority's requirement.
3. *Run the live test automatically whenever `ANTHROPIC_API_KEY`
   happens to be present in the environment* — rejected: `LIVE_TEST_MODE`
   is a second, independent, explicit gate specifically so an API key
   present for some *other* reason (a developer's shell profile) never
   silently triggers a billed call nobody asked for in this run.

**Consequences:** `router/python/avishkar_router/types.py`,
`router.py`, `providers/anthropic_provider.py`, and
`schemas/completion-response.schema.json` gained one additive field
each (`request_id`); `layla/python/avishkar_layla/types.py` and
`delegation.py` gained `DelegationRecord.cost_usd`. One new test file,
skipped by default, zero regressions (190 Layla tests, up from 189,
189 passing + 1 skipped; router's own 42 tests still pass unmodified).
`docs/live-integration-guide.md` gives exact execution instructions.
What remains true after this priority: the platform's live-external-
call coverage is exactly one test, exercised zero times against a real
key during this work — real, ready, and honestly reported as such, not
inflated into a claim of verified live behavior.
