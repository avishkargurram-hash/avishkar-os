# Prompt Framework — Contract

Language-agnostic contract for the Prompt Framework. The Python
reference implementation is `avishkar_prompt`
(`factories/prompt-factory/python/`).

## §1. PromptVersion

`PromptVersion(version, template, variables, target_models=())` — a
prompt is never a bare string; it's this structured, versioned type.
`template` is a `str.format`-style string (`{variable_name}`
placeholders) — stdlib-only, no template-engine dependency, consistent
with the platform's zero-dependency-by-default rule.

`variables: Tuple[PromptVariable, ...]` where `PromptVariable(name,
description, required=True)`. **Validated at `PromptVersion`
construction**: every `{name}` placeholder actually present in
`template` must be declared in `variables` (`UnknownVariableError`
otherwise) — this catches a typo'd placeholder at prompt-authoring time,
not at render time in production.

## §2. Rendering

`render(version, values) -> str`. Every `required=True` variable must
be present in `values` or `MissingVariableError` is raised — a prompt
never silently renders with a hole in it. Extra keys in `values` that
aren't declared variables are ignored (a caller passing a shared
context dict to several prompts shouldn't have to slice it per-prompt).

## §3. PromptRegistry

`PromptRegistry()` holds named prompts, each an ordered list of
`PromptVersion`s. `.register(name, version)` — `DuplicateVersionError`
if that `(name, version.version)` pair already exists; a version is
immutable once registered, matching the "a prompt change is a new
version, never a silent overwrite" responsibility in README.md.
`.get(name, version=None)` returns the named version, or the most
recently registered one if `version` is omitted. `.render(name, values,
version=None)` composes `.get()` + `render()`.

## §4. Scoring seam (forward-compatible with Phase 11 Evaluation Framework)

`Scorer = Callable[[str, EvalCase], float]` — scores rendered text
against one `EvalCase(inputs, expected)`, returning `0.0`–`1.0`.
`evaluate_version(registry, name, version, cases, scorer) ->
EvalReport(scores, average)` runs every case through `render()` then
`scorer`.

This framework ships two real, useful scorers today
(`exact_match_scorer`, `keyword_presence_scorer`) — not stubs — but
**does not** attempt to be the platform's evaluation framework. That's
Phase 11's `evaluation-factory`, deferred behind this one in the
locked build order. The seam is deliberately just a plain `Callable`,
the same "typed placeholder a later framework resolves" pattern
`agent-factory`'s `MCPToolRef` used for `mcp-factory` (ADR-0010/0011):
Phase 11 adds richer `Scorer` implementations (semantic similarity,
LLM-graded, regression-suite runners) that plug into this exact
`evaluate_version` signature with zero changes to this framework.

## §5. Regression comparison

`compare_versions(report_a, report_b) -> RegressionResult(improved,
delta)` — `delta = report_b.average - report_a.average`, `improved =
delta > 0`. Closes README.md's "diff/compare tooling between prompt
versions against the same eval suite" responsibility with a real,
tested function, not a promise.

## §6. Errors

`PromptFrameworkError` (base), `UnknownVariableError`,
`MissingVariableError`, `DuplicateVersionError`, `UnknownVersionError`.

## §7. Agent Framework integration

No new type is needed on `agent-factory`'s side: a domain module renders
a prompt via `PromptRegistry.render(...)` and passes the resulting
string as `Task.input` — `Task.input` is already `str` (Phase 3,
locked). This framework is a pure producer of strings `agent-factory`
already knows how to consume; no bridge module is required (contrast
with `workflow-factory`'s bridges, which were needed because
`ChiefDomainAgent`, `KnowledgeBase`, and `MemoryPolicy` are not
strings).
