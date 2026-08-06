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
