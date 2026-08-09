# Template Framework — Contract

Language-agnostic contract for the Template Framework. The Python
reference implementation is `avishkar_template`
(`factories/template-factory/python/`).

## §0. Boundary with `prompt-factory` and `documentation-factory`

`prompt-factory` (Phase 8) owns prompt text consumed by agents.
`template-factory` owns document/project templates instantiated to a
target path as real files — READMEs, ADRs, config boilerplate. Both
need the exact same primitive underneath (a string with declared,
validated `{variable}` placeholders), so this framework **reuses
`avishkar_prompt.PromptVersion`/`PromptVariable`/`render()` verbatim
rather than redefining them** — a `TemplateFile` is a `relative_path`
plus a `PromptVersion` (§1). `documentation-factory` (still deferred,
ADR-0009) is different again: doc-coverage *enforcement* (lint that
existing READMEs match the current template), not template *content* —
this framework produces the content; that one would check conformance
against it.

## §1. TemplateFile

`TemplateFile(relative_path, spec)` where `spec: PromptVersion`
(reused from `prompt-factory`) supplies the file's content template and
declared variables, with the exact same construction-time validation
(`UnknownVariableError` if `spec.template` references an undeclared
`{name}`).

## §2. Template

`Template(name, version, files)` — a named, versioned, ordered
collection of `TemplateFile`s (a "module README template" is one file;
a "starter project skeleton" could be many). Constructor validates
`relative_path` values are unique within the template
(`DuplicateFileError`).

## §3. TemplateRegistry

`TemplateRegistry()` — same shape as `prompt-factory`'s
`PromptRegistry`: `.register(name, template)`
(`DuplicateVersionError` on a repeat `(name, version)`),
`.get(name, version=None)`, `.versions(name)`.

## §4. Instantiation

`instantiate(template, target_dir, values, *, overwrite=False) ->
Tuple[Path, ...]` — renders every `TemplateFile` (via
`avishkar_prompt.render`) and writes it under `target_dir /
relative_path`, creating parent directories as needed. **Never
silently overwrites an existing file** — `TemplateInstantiationError`
if a target path already exists and `overwrite=False` (security/
safety-first: instantiating a template into a directory with existing
work must be an explicit, opt-in choice, not a default). Returns the
paths actually written, in file order.

## §5. Built-in template

Ships one real, working `Template`: the Module documentation template
from `STANDARDS.md` §2.1, formalized as
`avishkar_template.builtin.MODULE_README_TEMPLATE` — the same content
every shelf-package README in this repo (`memory/README.md`,
`knowledge/README.md`, `workflows/README.md`, `templates/README.md`)
already follows by hand. This closes the "formalize the de facto first
template" gap this framework's own pre-Phase-9 README placeholder
noted, with a real, tested, instantiable `Template` — not a second copy
of the prose pasted into a constant.

## §6. Errors

`TemplateFrameworkError` (base), `DuplicateFileError`,
`DuplicateVersionError` (reused name, same meaning as `prompt-factory`'s
— a `(name, version)` pair already registered), `UnknownVersionError`,
`TemplateInstantiationError`.
