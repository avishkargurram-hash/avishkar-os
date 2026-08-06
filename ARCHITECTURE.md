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
| `mcp-factory` | MCP servers exposing tools/resources to agents |
| `langgraph-factory` | LangGraph graph scaffolds (stateful agent graphs) |
| `n8n-factory` | n8n automation flows |
| `starter-kit-factory` | End-to-end starter kits for common product shapes |
| `knowledge-factory` | Knowledge base / retrieval pipeline scaffolds |
| `memory-factory` | Memory backend schemas & adapters |
| `evaluation-factory` | Eval harnesses and scoring rubrics for agents/prompts |
| `security-factory` | Security review tooling, threat-model templates, guardrail policies |

Each factory is documented per [STANDARDS.md](./STANDARDS.md)'s module
documentation template: Purpose, Responsibilities, Architecture, Inputs,
Outputs, Dependencies, Examples, Limitations, Future improvements.

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
(e.g. "Coding", "Research", "Support") and internally supports multiple
expert *roles* within that domain via role/persona configuration, not by
spawning a new top-level agent per role. Before adding a new agent to
`agents/`, the bar is: *"Is this a genuinely new domain, or a new role an
existing Chief Agent should absorb?"* Default to absorption.

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

## 6. Applications are external

Tryvanta, Humanify OS, GENESIS, Muziclly, AI Atlas, Coupler, and future
products are **separate repositories**, scaffolded via `starters/` or
`factories/project-factory`, that consume Avishkar OS as a dependency (or
git submodule / package, decided per ADR). They are not folders inside this
repo.

## 7. Status

This is the initial scaffold. Every directory currently exists as
structure + a README describing its contract; implementation lands
module-by-module per [ROADMAP.md](./ROADMAP.md). Structure was written
first, deliberately — see [DECISIONS.md](./DECISIONS.md) ADR-0001.
