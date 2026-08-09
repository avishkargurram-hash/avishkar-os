# framework-readme

## Purpose
Formalizes STANDARDS.md §2.2's Framework template — the shape every
`factories/*`, `core/`, and `router/` README already follows by hand —
as a real, instantiable `Template`. The first concrete shelf artifact
under `templates/` (Phase 14) beyond `template-factory`'s own built-in
Module template, closing that framework's own README Future Roadmap
item explicitly.

## Responsibilities
- Ship `FRAMEWORK_README_TEMPLATE`, a real `template-factory`
  `Template` matching STANDARDS.md §2.2 exactly.
- Stay in sync with STANDARDS.md — a change to §2.2's section list
  should update this template in the same PR.

## Architecture
One `TemplateFile` (`README.md`) wrapping a `PromptVersion` whose
template text is STANDARDS.md §2.2 verbatim, with `<Name>` replaced by
the `{framework_name}` placeholder. Built on `template-factory`'s real
`Template`/`TemplateFile`/`instantiate()` (Phase 9) and
`prompt-factory`'s `PromptVersion` (Phase 8) — no new architecture.

## Interfaces
`FRAMEWORK_README_TEMPLATE: Template`. Instantiate with
`avishkar_template.instantiate(FRAMEWORK_README_TEMPLATE, target_dir,
{"framework_name": "..."})`.

## Dependencies
`core/`, `factories/prompt-factory`, `factories/template-factory`.

## Inputs
One value: `framework_name`.

## Outputs
A `README.md` matching STANDARDS.md §2.2's ten sections, ready to fill
in.

## Examples
`python templates/framework-readme/examples/quickstart.py` —
instantiates the template for a hypothetical "Notification" framework.

## Limitations
Only the Framework tier (§2.2) is formalized here. The Chief Domain
Agent tier (§2.3, 30 sections) remains hand-authored per agent — real
future work, not hidden.

## Future Roadmap
- Formalize the Chief Domain Agent template (§2.3) the same way, once
  a twelfth agent (requiring a new ADR per ADR-0007) makes reuse worth
  the investment — with 11 agents already hand-authored, the marginal
  value today is lower than it was for the Framework tier.
