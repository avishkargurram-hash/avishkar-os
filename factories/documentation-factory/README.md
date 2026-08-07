# Documentation Framework

## Vision
Every folder in Avishkar OS must contain meaningful documentation — not as
a courtesy, but as a load-bearing part of the architecture: an AI agent or
engineer navigating this repo has no source of truth beyond what's
written down. Documentation Framework makes that a checkable, enforced
property of the platform rather than a habit that erodes as the repo
grows. It is distinct from [`template-factory`](../template-factory/README.md),
which produces content templates (PRD, API doc, architecture doc) that
*products* fill in — this framework enforces the platform's *own*
documentation, against itself. See [DECISIONS.md](../../DECISIONS.md)
ADR-0005 for why this is a separate framework, not a `template-factory`
responsibility.

## Architecture
_(To be designed in Phase 5 — see [ROADMAP.md](../../ROADMAP.md).)_
Expected shape: a CLI/CI check that walks the repo, classifies each
directory (module / framework / Chief Domain Agent / plain directory) by
where it sits in the tree, and validates its README against the matching
[STANDARDS.md](../../STANDARDS.md) §2 template — every required section
present and non-empty, not merely that a README file exists.

## Folder Structure
```
factories/documentation-factory/
├── README.md          this file
├── checks/            (planned) doc-coverage & template-conformance rules
└── cli/                (planned) `avishkar docs check` / `avishkar docs new`
```

## Naming Standards
Follows the platform-wide conventions in [STANDARDS.md](../../STANDARDS.md)
§3. No framework-specific naming rules beyond that.

## Interfaces
_(Not implemented yet.)_ Planned: `avishkar docs check [path]` (exit
non-zero on missing/incomplete README, used as a CI gate) and
`avishkar docs new --tier <module|framework|agent> <path>` (scaffolds a
correctly-templated README so no one hand-copies a template and drifts
from it).

## Extension Model
A new documentation tier (beyond Module/Framework/Chief Domain Agent) is
added by: (1) defining its template in STANDARDS.md §2, (2) recording the
ADR, (3) adding a classifier rule here so `docs check` recognizes which
directories the new tier applies to.

## Examples
_(none yet — this framework doesn't exist as running code. Its own
existence is documented honestly as not-yet-built, which is exactly the
kind of gap it will eventually catch for every *other* module too.)_

## Best Practices
- Run `docs check` before opening a PR, once it exists, rather than
  relying on reviewer memory.
- Treat a failing doc-coverage check the same as a failing test — fix the
  doc, don't suppress the check.

## Anti-Patterns
- Writing a README that copies a template's headings but leaves sections
  as placeholder filler ("TBD") to pass a shallow "file exists" check —
  the planned validator checks non-emptiness and should eventually check
  for exactly this pattern.
- Letting `docs/` (the shelf) accumulate content that duplicates what a
  module's own README should say — see [docs/README.md](../../docs/README.md).

## Future Roadmap
- Phase 5 (see [ROADMAP.md](../../ROADMAP.md)): implement `docs check` as
  a CI gate; retroactively audit every README written before this
  framework existed (all 24 from the initial scaffold, plus this one)
  against the correct template tier.
