# Architecture

This document explains how Avishkar OS is structured and — more importantly
— *why*. Structure without reasoning is just folders. Every boundary below
exists to answer a specific question a future engineer (human or AI) will ask.

Changes to this document require a corresponding entry in [DECISIONS.md](./DECISIONS.md).

---

## 1. The one rule: no business logic in the platform

Avishkar OS answers "how do we build AI systems well?" — never "what does
Tryvanta do?" The moment product-specific logic (a prompt tuned for one
app's tone, a workflow that only makes sense for one customer flow) enters
this repo, the platform stops being reusable and starts being product code
wearing a platform costume. That logic belongs in the product's own
repository, which *depends on* Avishkar OS.

**Test before adding anything here:** *"Would a second, unrelated product
also want this, unmodified or lightly configured?"* If no, it doesn't
belong in Avishkar OS.

## 1.5 "Framework" and "Factory" are the same folder, different resolution

The Master Build Directive calls these 16 modules "Frameworks"; ADR-0002
called them "Factories." Both names point at the same folders — see
[DECISIONS.md](./DECISIONS.md) ADR-0005. A **Framework** is a factory (or
platform-wide capability like `core/`/`router/`/`layla/` — see ADR-0020
for why Layla, added in Phase 16, is a third member of this category
rather than a factory or a Chief Domain Agent) documented and built to
the fuller bar in [STANDARDS.md](./STANDARDS.md) §2.2 (Vision, Folder
Structure, Naming Standards, Extension Model, Best Practices,
Anti-Patterns), not a different or renamed directory. Use "Framework" when
talking about the capability's depth and maturity; "Factory" when talking
about its mechanical role as a generator (§2 below). Folder names stay as
originally built (`factories/agent-factory`, not `frameworks/agent-framework`)
— see ADR-0005 for why a mechanical rename was rejected.

## 2. Factories vs. Library — two different kinds of directory

The repository has two directory families that look similar but serve
opposite purposes. This split is the most important architectural decision
in this repo, so it's spelled out explicitly (see [DECISIONS.md](./DECISIONS.md) ADR-0002):

| | `factories/*` | `agents/`, `templates/`, `workflows/`, `knowledge/`, `memory/`, `router/`, `mcp/`, `langgraph/`, `automation/`, `starters/` |
|---|---|---|
| **Role** | Generators / meta-tooling | Library of built, reusable, production artifacts |
| **Answers** | "How do we *build* a new agent / prompt / workflow?" | "What agents / prompts / workflows already exist and are ready to use?" |
| **Consumes** | Specs, blueprints, CLI args | Nothing — these ARE the finished output |
| **Produced by** | Hand-written, by platform engineers | Generated (or scaffolded) by the matching factory, then hardened and committed |
| **Changes when** | The *process* of building something improves | A new reusable capability ships, or an existing one is upgraded |

Concretely: `factories/agent-factory/` contains the generator, blueprints,
and CLI that scaffold a new Chief Domain Agent. Its *output* — the actual,
production-ready Chief Domain Agents every product can import — lives in
`agents/`. The factory is the mold; the top-level directory is the shelf of
finished parts. Without this split, every factory would become a junk
drawer of both tooling and output, and reusable artifacts would be
impossible to find without knowing which factory produced them.

Not every factory has a matching top-level shelf:

- **`project-factory`** scaffolds entire *new repositories* (e.g. a fresh
  product repo wired to Avishkar OS). Its output isn't stored here — it's
  a new repo elsewhere.
- **`evaluation-factory`** and **`security-factory`** produce eval suites
  and security policies/tooling that are cross-cutting — consumed directly
  inside `core/`, `router/`, and each product, rather than collected in a
  dedicated shelf. If a clear "shelf" need emerges (e.g. a shared
  `evals/` library of eval sets), add it deliberately via an ADR, not by
  default.

## 3. Module responsibilities

### `factories/` — reusable generators

| Factory | Produces |
|---|---|
| `agent-factory` | Chief Domain Agents (see §4) |
| `prompt-factory` | Versioned, evaluable prompt templates |
| `template-factory` | Reusable doc/code/project templates |
| `workflow-factory` | Multi-step orchestrated workflows |
| `project-factory` | New product repositories pre-wired to Avishkar OS |
| `mcp-factory` | "Universal Integration Framework" (ADR-0011) — a protocol-agnostic tool platform (`ProtocolAdapter`, `UniversalToolRegistry`, `ToolRuntime`) with MCP as its first-class, production implementation and a second real adapter (REST) proving the abstraction is genuine |
| `langgraph-factory` | LangGraph graph scaffolds (stateful agent graphs) |
| `n8n-factory` | n8n automation flows |
| `starter-kit-factory` | End-to-end starter kits for common product shapes |
| `knowledge-factory` | Knowledge base / retrieval pipeline scaffolds |
| `memory-factory` | Memory backend schemas & adapters |
| `evaluation-factory` | Eval harnesses and scoring rubrics for agents/prompts |
| `security-factory` | Security review tooling, threat-model templates, guardrail policies |
| `documentation-factory` | Doc-coverage enforcement, README/ADR tooling — the platform's *own* documentation compliance (see [DECISIONS.md](./DECISIONS.md) ADR-0005; distinct from `template-factory`, which produces content templates products fill in) |

14 factories, plus `core/` ("Core Engine Framework") and `router/` ("AI
Router Framework") — 16 Frameworks total (§1.5).

Each factory/framework is documented per [STANDARDS.md](./STANDARDS.md)
§2.2's Framework template: Vision, Architecture, Folder Structure, Naming
Standards, Interfaces, Extension Model, Examples, Best Practices,
Anti-Patterns, Future Roadmap.

### The library shelves

- **`agents/`** — Production Chief Domain Agents. See §4.
- **`templates/`** — Finished, reusable templates (prompt, doc, project).
- **`workflows/`** — Finished, reusable orchestrated workflows.
- **`knowledge/`** — Shared knowledge bases and retrieval sources usable
  across products (not product-specific data).
- **`memory/`** — Shared memory backend implementations and schemas
  (short-term, long-term, episodic) that products configure, not fork.
- **`router/`** — The AI Router: model/provider selection, cost/latency
  routing, fallback chains. The single place that decides "which model
  handles this request."
- **`mcp/`** — Reusable MCP servers products can mount.
- **`langgraph/`** — Reusable LangGraph graphs for common agentic patterns.
- **`automation/`** — Reusable n8n flows for operational automation.
- **`starters/`** — Clone-and-go starter kits.
- **`core/`** — The Core Engine: the minimal runtime substrate (config,
  logging, event bus, lifecycle, plugin/module loading) every other module
  depends on. `core/` depends on nothing else in this repo; everything else
  may depend on `core/`. This is a hard dependency direction, not a
  convention — violating it is an architecture bug.
- **`docs/`** — Deep documentation that outgrows a single module's README
  (design explorations, cross-cutting guides, onboarding).

## 4. Chief Domain Agents, not agent sprawl

Per the constitution: build only reusable **Chief Domain Agents**, never
dozens of narrow single-purpose agents. Each Chief Agent owns one domain
and internally supports multiple expert *roles* within that domain via
role/persona configuration, not by spawning a new top-level agent per
role. Before adding a new agent to `agents/`, the bar is: *"Is this a
genuinely new domain, or a new role an existing Chief Agent should
absorb?"* Default to absorption.

The roster is locked (see [DECISIONS.md](./DECISIONS.md) ADR-0007) to
exactly these 11 packages under `agents/`:

1. `agents/software-ai-engineering/`
2. `agents/medical-healthcare/`
3. `agents/legal-compliance/`
4. `agents/startup-business-product/`
5. `agents/education-knowledge/`
6. `agents/research-intelligence/`
7. `agents/finance-economics/`
8. `agents/government-public-policy/`
9. `agents/human-development-psychology/`
10. `agents/creative-media/`
11. `agents/orchestrator/` — decides which domain agent(s) collaborate on
    a given task; the only agent whose "domain" is the roster itself.
    Its coordination *mechanics* (routing, hierarchical delegation,
    swarm broadcast, conflict resolution) already ship as
    `agent-factory`'s `Orchestrator` class — a framework capability every
    product can use today with any registered `ChiefDomainAgent`s. The
    `agents/orchestrator/` *package* is that engine's own 30-section
    Chief Domain Agent write-up (mission, guardrails, communication
    style, ...) plus any orchestrator-specific defaults — not a
    reimplementation.

A 12th agent (a genuinely new domain, not a role) requires its own ADR.
Each is documented to [STANDARDS.md](./STANDARDS.md) §2.3's Chief Domain
Agent template (expanded to 30 sections per
[DECISIONS.md](./DECISIONS.md) ADR-0010). 1 of 11 is built —
`agents/software-ai-engineering/` (ROADMAP.md Phase 3); the rest follow
one at a time, see [ROADMAP.md](./ROADMAP.md).

## 5. Dependency direction

```
core/  ←── everything (nothing depends on nothing; core depends on nothing internal)
factories/*  ──produce──►  agents/ templates/ workflows/ knowledge/ memory/ mcp/ langgraph/ automation/ starters/
router/  ──used by──►  agents/, workflows/, applications
applications (Tryvanta, GENESIS, ...)  ──depend on──►  Avishkar OS (never the reverse)
```

Avishkar OS never imports from an application. If that ever seems
necessary, the logic being pulled in is product logic that was placed in
the platform by mistake — move it, don't import it back.

**A later-built framework may depend on an earlier one** — dependency
direction is about layering (core → everything; applications never
depended-on), not build order. `mcp-factory` (Phase 4) depends on
`agent-factory` (Phase 3) for its Agent Integration bridge
(`resolve_mcp_tool_ref`, and reusing `ApprovalGate`/`MemoryPolicy`
rather than duplicating them) — see [DECISIONS.md](./DECISIONS.md)
ADR-0011 §7. `agent-factory`'s own source stays unmodified; the new
dependency is added by the consumer (`mcp-factory`) reaching for it, not
by reopening a locked framework.

## 6. Applications are external

Tryvanta, Humanify OS, GENESIS, Muziclly, AI Atlas, Coupler, and future
products are **separate repositories**, scaffolded via `starters/` or
`factories/project-factory`, that consume Avishkar OS as a dependency (or
git submodule / package, decided per ADR). They are not folders inside this
repo.

## 7. Status

As of 2026-08-09 (Phase 15, Final Integration), the structure this
document describes was fully implemented, not just scaffolded: every
`factories/*` entry (12 built, 4 documented-but-deferred per
[DECISIONS.md](./DECISIONS.md) ADR-0009), `core/`, `router/`, and all
11 locked-roster `agents/*` (ADR-0007) are real code with contracts,
tests, and runnable examples — not README-only structure. The library
shelves (`memory/`, `knowledge/`, `workflows/`, `templates/`,
`starters/`) each hold at least one concrete, product-facing instance
as of Phase 14, in addition to the reusable engines living in their
owning factories.

Phase 16 (2026-08-11) added `layla/` — Avishkar OS's Personal
Executive Intelligence layer — as a third platform-wide capability
alongside `core/`/`router/` (ADR-0020): a client of every other
framework's public contract, never a duplicate of one. Phase 17
(2026-08-11) hardened it across five priorities — authentication/
authorization, idempotency, resume-in-place/durable execution,
concurrency, and controlled live integration validation (ADR-0021
through ADR-0025) — including a narrow, documented, additive exception
to `core/`'s and two factories' otherwise-locked status where the
Phase 17 directive explicitly named them as audit/harden targets (see
ADR-0024). The platform now stands at 732 tests, 731 passing plus one
deliberately skipped by design (a live-API test gated behind explicit
opt-in credentials).

See [docs/final-integration.md](./docs/final-integration.md) for a
real, cross-cutting proof that the Phase 1–15 pieces connect,
[docs/production-readiness.md](./docs/production-readiness.md) for an
honest account of what is and isn't production-ready after Phase 17,
and [ROADMAP.md](./ROADMAP.md) for the full build history.
