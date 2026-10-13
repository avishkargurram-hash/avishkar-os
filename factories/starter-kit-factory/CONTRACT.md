# Starter Kit Framework — Contract

Language-agnostic contract for the Starter Kit Framework. The Python
reference implementation is `avishkar_starter_kit`
(`factories/starter-kit-factory/python/`).

## §0. What a StarterKit actually contains

A starter kit demonstrates a **working product shape** — it is not a
serialized object graph. Some of what it composes (an `AgentBlueprint`)
is real, portable, declarative data and gets written out as-is. Other
things it composes (a `WorkflowEngine` run, a live `KnowledgeBase`) are
bound to runtime objects (Python closures, in-process instances) that
cannot be meaningfully serialized across a process boundary — trying to
pickle a `WorkflowSpec`'s step closures into a "reusable" kit would be
fake portability, not real. Instead, the starter kit's generated
`main.py` (a `TemplateFile`, `template-factory`) **is** the composition:
real, runnable source code that wires a `ChiefDomainAgent`, a memory
backend, a knowledge base, and a `WorkflowEngine` together using this
platform's actual public APIs. A cloned kit is a working program, not a
frozen snapshot of one.

## §1. StarterKit

`StarterKit(name, version, description, blueprint, project_template,
components=())` — `blueprint: avishkar_agent.AgentBlueprint` (real,
portable declarative data), `project_template:
avishkar_template.Template` (the files that make the kit clone-and-go:
`pyproject.toml`, `README.md`, `main.py`, `.gitignore`), `components` a
plain `Tuple[str, ...]` documenting which platform pieces the generated
`main.py` demonstrates wiring together (e.g. `("agent", "memory",
"knowledge", "workflow")`) — for humans and tooling to inspect without
parsing source, not a live reference.

## §2. StarterKitRegistry

Same shape as `PromptRegistry`/`TemplateRegistry`:
`.register(name, kit)` (`DuplicateVersionError` on a repeat
`(name, version)`), `.get(name, version=None)`, `.versions(name)`.

## §3. Materialization

`materialize(kit, target_dir, values) -> StarterKitResult(written)`:
1. `avishkar_template.instantiate(kit.project_template, target_dir,
   values)` — writes every project file (README, pyproject.toml,
   main.py, ...), reusing Phase 9's instantiation semantics verbatim
   (all-or-nothing on collision, `overwrite=False` by default).
2. Writes `target_dir/agent/blueprint.json` —
   `dataclasses.asdict(kit.blueprint)` as JSON — the one piece of a
   Chief Domain Agent that *is* portable data (Phase 3's own
   `AgentBlueprint.from_file()` can read it straight back). Checked for
   a pre-existing collision under the same `overwrite` rule as step 1,
   raising `avishkar_template.TemplateInstantiationError` (reused, not
   redefined) before anything is written.
3. Returns every path written, in order.

## §4. Relationship to `project-factory` (deferred, ADR-0009)

This framework produces starter kit *content*
(`starters/<kit-name>/`). `project-factory` — which would scaffold an
entire new git repository from a kit — remains deferred; nothing here
depends on it, and `materialize()` already writes a real, working
directory tree without needing it. When `project-factory` is scheduled,
it becomes a thin consumer of `materialize()` plus repo/CI bootstrapping
this framework deliberately does not attempt.

## §5. Errors

`StarterKitFrameworkError` (base), `DuplicateVersionError`,
`UnknownVersionError` (both reused-shaped from `template-factory`/
`prompt-factory`'s own errors, same meaning).
