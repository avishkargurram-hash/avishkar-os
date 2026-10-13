"""Platform Standards knowledge base -- the first concrete, product-facing
KnowledgeBase committed under knowledge/ (Phase 14), rather than only a
factory-package example. Seeded with real excerpts from this
repository's own STANDARDS.md/ARCHITECTURE.md, genuinely reusable by
any product built on Avishkar OS whose own agents need awareness of
platform conventions -- not a demo, the actual governance content.
"""

from __future__ import annotations

from avishkar_knowledge import KnowledgeBase

_DOCUMENTS = {
    "engineering-principles": (
        "SOLID, Clean Architecture, DDD where it earns its complexity, DRY, "
        "KISS, YAGNI, composition over inheritance, convention over "
        "configuration, documentation-first, reusable-first, "
        "automation-first, security-first. Before writing code, ask in "
        "order: does this already exist somewhere in the platform (DRY); "
        "am I building the simplest thing that satisfies the actual "
        "requirement, not an imagined future one (KISS/YAGNI); can a "
        "second product use this unmodified or via config (reusable-first); "
        "is the responsibility of this module still exactly one sentence "
        "(SOLID-S)."
    ),
    "documentation-templates": (
        "Three documentation tiers apply depending on what's being "
        "documented: the Module template for a single shelf package, the "
        "Framework template for every factories/*, core/, and router/ "
        "package, and the 30-section Chief Domain Agent template for "
        "every agents/*. All sections are required, in order; a section "
        "that genuinely doesn't apply says so explicitly rather than "
        "being omitted."
    ),
    "security-checklist": (
        "No secrets, API keys, or credentials committed, ever -- "
        ".env.template documents required variables, .env is git-ignored. "
        "Every MCP server and agent tool that touches external systems "
        "goes through the security guardrail/threat-model checklist "
        "before it is marked reusable."
    ),
    "naming-conventions": (
        "Directories use kebab-case (e.g. agent-factory, "
        "starter-kit-factory). Python packages and modules use "
        "snake_case. TypeScript files use kebab-case.ts."
    ),
    "commit-and-review-discipline": (
        "Commits are scoped to one logical change; the message states "
        "what and, where non-obvious, why. Structural or "
        "dependency-direction changes require an ADR before the PR, not "
        "after. No file is added just in case -- if you can't fill in its "
        "README's Purpose section honestly, don't create it yet."
    ),
}


def build_platform_standards_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    for document_id, text in _DOCUMENTS.items():
        kb.ingest(document_id, text)
    return kb
