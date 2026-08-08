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
