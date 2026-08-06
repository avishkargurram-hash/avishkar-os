# Template Factory

## Purpose
Generates reusable **document and project templates** (READMEs, ADRs,
module contracts, boilerplate configs) — the tooling that produces
non-prompt templates landing in [`templates/`](../../templates/README.md).
Prompt templates specifically are owned by `prompt-factory`, not here —
see that factory's README for the boundary.

## Responsibilities
- Maintain the canonical module README template defined in
  [STANDARDS.md](../../STANDARDS.md) §2, and any other doc templates
  (ADR template, RFC template) referenced from DECISIONS.md/CONTRIBUTING.md.
- Scaffold boilerplate project structure fragments (e.g. a standard
  `.gitignore`, CI config skeleton) reused across product repos created via
  `project-factory` / `starter-kit-factory`.
- Keep templates in sync when standards change — a STANDARDS.md edit that
  changes the README template should be reflected here in the same PR.

## Architecture
_(To be designed in Phase 4.)_ Expected shape: a small library of
Markdown/config templates with placeholder tokens, plus a thin CLI to
instantiate one into a target path.

## Inputs
A template request (which template, target path, values for placeholders).

## Outputs
Instantiated files, and the canonical template sources themselves living
under `templates/docs/` and `templates/project/`.

## Dependencies
`core/` only.

## Examples
_(none yet — the module README template in STANDARDS.md §2 is the
de facto first template; formalizing it here is Phase 4 work.)_

## Limitations
Not implemented yet. Until it is, STANDARDS.md's inline template is the
source of truth — don't let it silently drift once this factory exists.

## Future improvements
- Lint that every module README in the repo actually matches the current
  template version.
