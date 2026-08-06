# Prompt Factory

## Purpose
Generates versioned, evaluable prompt templates — the tooling that turns a
prompt spec into a reusable asset in [`templates/`](../../templates/README.md),
not the prompts themselves.

## Responsibilities
- Define the prompt template schema: variables, expected model(s),
  versioning, and a link to the eval suite that scores it.
- Scaffold a new prompt template with placeholders for variables,
  few-shot examples, and its eval reference.
- Enforce that every prompt template is versioned (no silent overwrites —
  a prompt change is a new version, evaluated before promotion).
- Diff/compare tooling between prompt versions against the same eval suite.

## Architecture
_(To be designed in Phase 4 — see [ROADMAP.md](../../ROADMAP.md).)_
Expected shape: prompt templates as structured files (not raw strings)
with metadata (version, target model(s), variables, eval suite id),
consumed by `agents/` and product code via a small runtime loader in
`core/`.

## Inputs
A prompt spec: intent, variables, target model(s), and (ideally) example
inputs/outputs to seed the eval suite.

## Outputs
A versioned prompt template package in `templates/prompts/<name>/`.

## Dependencies
`evaluation-factory` (every prompt needs a scoring path before it's
"reusable," not just "written"), `router/` (target model constraints).

## Examples
_(none yet.)_

## Limitations
Not implemented yet.

## Future improvements
- Automatic regression check: a new prompt version can't ship if it scores
  worse than the previous version on the same eval suite without an
  explicit override + reason.
