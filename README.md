# Avishkar OS

**The reusable AI Engineering Platform that powers every Avishkar Labs product.**

Avishkar OS is not a product. It contains **no business logic**. It is the
shared foundation — factories, agents, routing, memory, knowledge, and
standards — that every Avishkar Labs application (Tryvanta, Humanify OS,
GENESIS, Muziclly, AI Atlas, Coupler, and whatever comes next) is built on
top of.

If a capability is useful to more than one product, it belongs here. If it's
specific to one product, it belongs in that product's own repository, built
*using* Avishkar OS.

## Start here

| Document | What it answers |
|---|---|
| [CLAUDE.md](./CLAUDE.md) | The Master Constitution — engineering principles and how Claude Code (or any engineer) should operate in this repo. |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | How the system is structured, and *why* — the Factories vs. Library split, module responsibilities, boundaries. |
| [STANDARDS.md](./STANDARDS.md) | Coding, documentation, naming, and review standards enforced across every module. |
| [ROADMAP.md](./ROADMAP.md) | What exists, what's being built, what's next. |
| [DECISIONS.md](./DECISIONS.md) | The append-only architecture decision log (ADRs). *Why* things are the way they are. |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | How to propose and land a change, including new factories or modules. |
| [CHANGELOG.md](./CHANGELOG.md) | What shipped, release by release. |

## Repository layout

```
Avishkar-OS/
├── factories/     # Meta-tooling: generators that PRODUCE agents, prompts, templates, workflows, etc.
├── agents/        # Reusable, production Chief Domain Agents (built via agent-factory)
├── templates/     # Reusable prompt/project/doc templates (built via template-factory)
├── workflows/      # Reusable multi-step workflows (built via workflow-factory)
├── knowledge/     # Shared knowledge bases / retrieval sources (built via knowledge-factory)
├── memory/        # Shared memory backends & schemas (built via memory-factory)
├── router/        # AI Router — model/provider selection and fallback logic
├── mcp/           # Reusable MCP servers (built via mcp-factory)
├── langgraph/     # Reusable LangGraph graphs (built via langgraph-factory)
├── automation/    # Reusable n8n flows (built via n8n-factory)
├── starters/      # Ready-to-clone starter kits for new products (built via starter-kit-factory)
├── core/          # Core Engine — the runtime substrate everything else plugs into
└── docs/          # Deep-dive documentation that doesn't belong in a single module
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for why `factories/` and its
sibling directories are two different things, not a duplication.

## Status

As of 2026-08-11, all 15 originally-planned phases are locked, plus
Phase 16 (Layla — Avishkar OS's Personal Executive Intelligence layer,
[layla/](./layla/)) and Phase 17 (Hardening & Production Readiness:
identity/authorization, idempotency, resume-in-place, concurrency
hardening, and controlled live integration validation) — **732 tests
passing platform-wide** (731 passing + 1 deliberately skipped by
design — a live-API test gated behind explicit opt-in credentials),
zero known regressions. See
[docs/final-integration.md](./docs/final-integration.md) for a real,
runnable proof of how the core systems connect,
[docs/production-readiness.md](./docs/production-readiness.md) for an
honest account of what is and isn't production-ready today, and
[ROADMAP.md](./ROADMAP.md) for the full phase-by-phase history and
what's next.

## License

Proprietary — see [LICENSE](./LICENSE).
