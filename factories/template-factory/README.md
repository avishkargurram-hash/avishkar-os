# Template Framework

## Vision
Document and project templates (module READMEs, config boilerplate)
deserve the same rigor as prompts: declared variables, validated
placeholders, and safe instantiation to a real target path — not
copy-pasted prose or `cp -r` and manual find-replace. Template
Framework reuses `prompt-factory`'s validated-string primitive
verbatim and adds file/directory instantiation on top.

## Architecture
```
factories/template-factory/python/avishkar_template/
├── types.py          TemplateFile (wraps a PromptVersion) / Template (validated file collection)
├── registry.py         TemplateRegistry -- same shape as PromptRegistry
├── instantiate.py       instantiate(template, target_dir, values) -> written paths
└── builtin.py            MODULE_README_TEMPLATE -- STANDARDS.md SS2.1, formalized
```
See [CONTRACT.md](./CONTRACT.md) §0 for the boundary with `prompt-factory`
(owns prompt text) and `documentation-factory` (deferred; would lint
conformance against what this framework produces).

## Interfaces
`TemplateFile(relative_path, spec: PromptVersion)`. `Template(name,
version, files)` — validates unique `relative_path`s.
`TemplateRegistry().register(name, template)` /
`.get(name, version=None)`. `instantiate(template, target_dir, values,
overwrite=False) -> Tuple[Path, ...]`.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new template is just a `Template` built from `TemplateFile`s —
reusing `avishkar_prompt.PromptVersion` means variable declaration and
validation is already solved; this framework only adds the
file-writing step.

## Examples
`python factories/template-factory/examples/quickstart.py` —
instantiates the built-in Module README template for a real new
package, then registers and instantiates a custom two-file
`python-package-skeleton` template (`pyproject.toml` + `.gitignore`).

## Best Practices
- Prefer one `Template` with multiple `TemplateFile`s over several
  separate templates that always get instantiated together — keeps a
  "these files always ship as a set" relationship explicit and atomic
  (instantiation validates every file's target before writing any).
- Leave `overwrite=False` (the default) unless a caller has already
  confirmed the target directory is meant to be replaced.

## Anti-Patterns
- Redefining a `TemplateVariable`-like type instead of using
  `PromptVariable` — see CONTRACT.md §0 for why that would violate DRY
  for no benefit.
- Calling `instantiate()` in a loop with `overwrite=True` as a way to
  "sync" a directory to a template — it only writes declared files, it
  doesn't delete files that shouldn't be there; that's a different,
  unbuilt feature, not what this function does.

## Testing Strategy
15 tests: `TemplateFile`/`Template` construction (including proving
`PromptVersion`'s own `UnknownVariableError` fires — not a
reimplementation that happens to look similar), duplicate-file-path
validation, `TemplateRegistry` lifecycle (mirrors `PromptRegistry`'s
own test suite), `instantiate()` (nested directories, overwrite
refusal, overwrite acceptance, and — importantly — that a collision
anywhere blocks *all* writes rather than leaving a half-instantiated
directory), and the built-in Module README template (section-header
coverage + a real instantiation).

## Limitations
- **One built-in template today** — the Module README template
  (STANDARDS.md §2.1). The Framework template (§2.2) and Chief Domain
  Agent template (§2.3) are real, hand-maintained Markdown in
  STANDARDS.md but not yet formalized as `Template` objects here — real
  future work, not hidden.
- **No delete/sync semantics** — `instantiate()` only ever creates or
  (with `overwrite=True`) replaces declared files; it never removes a
  file that isn't part of the template. See Anti-Patterns.

## Future Roadmap
- Formalize the Framework (§2.2) and Chief Domain Agent (§2.3)
  templates from STANDARDS.md as `Template` objects, closing the same
  gap this phase closed for the Module template.
- A `documentation-factory` (deferred, ADR-0009) doc-coverage lint that
  checks an existing README actually matches the `Template` it should
  have been instantiated from.
