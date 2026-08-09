# Prompt Framework

## Vision
A prompt embedded as a raw string in a domain module is unversioned,
undiffable, and untestable. Prompt Framework turns it into a real
asset: a validated, versioned `PromptVersion`, rendered through a
`PromptRegistry`, scored against eval cases, and compared across
versions — the same rigor the rest of the platform applies to code,
applied to prompt text.

## Architecture
```
factories/prompt-factory/python/avishkar_prompt/
├── types.py       PromptVariable / PromptVersion (validated at construction) / EvalCase / EvalReport / RegressionResult
├── render.py        render(version, values) -> str
├── registry.py       PromptRegistry -- named, versioned, immutable-once-registered
├── scoring.py         Scorer seam + exact_match_scorer / keyword_presence_scorer + evaluate_version/compare_versions
└── errors.py
```
See [CONTRACT.md](./CONTRACT.md) for the full contract, including the
scoring seam's forward-compatibility with Phase 11's Evaluation
Framework (§4).

## Interfaces
`PromptVersion(version, template, variables, target_models=())` —
validates every `{var}` in `template` is declared. `render(version,
values) -> str`. `PromptRegistry().register(name, version)` /
`.get(name, version=None)` / `.render(name, values, version=None)`.
`evaluate_version(registry, name, version, cases, scorer) ->
EvalReport`. `compare_versions(report_a, report_b) -> RegressionResult`.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new `Scorer` is just a function matching `Callable[[str, EvalCase] ->
float]` — no base class, no registration. Phase 11's evaluation-factory
plugs richer scorers (semantic similarity, LLM-graded) into the exact
same `evaluate_version` call.

## Examples
`python factories/prompt-factory/examples/quickstart.py` — registers
two versions of a support-agent prompt, evaluates both against the same
eval case with `keyword_presence_scorer`, picks the winner via
`compare_versions`, and feeds its rendered text into a real
`ChiefDomainAgent`'s `Task.input`.

## Best Practices
- Declare every variable a template uses, even optional ones used only
  in some contexts — `PromptVersion`'s construction-time check exists
  specifically to catch a `{typo}` before it reaches production.
- Write eval cases before bumping a prompt's version, not after — the
  point of `compare_versions` is catching a regression before it ships,
  not documenting one after a user reports it.

## Anti-Patterns
- Mutating a `PromptVersion` in place (e.g. patching `.template`) instead
  of registering a new version — versions are immutable once registered
  (`DuplicateVersionError` on a repeat version string) specifically so a
  running system's behavior can't silently drift.
- Using `exact_match_scorer` for open-ended generative text — it's the
  right tool for deterministic templates, the wrong one for anything an
  LLM phrases differently each run; use `keyword_presence_scorer` or
  wait for Phase 11's richer scorers.

## Testing Strategy
24 tests: `PromptVersion` construction validation (undeclared variable
raises, unused-but-declared variable is fine), rendering (all-required-
present, missing-required raises, unknown extra keys ignored),
`PromptRegistry` (register/duplicate/get-latest/get-specific/unknown-
name/unknown-version/render), and scoring (`exact_match_scorer`,
`keyword_presence_scorer` including partial-match and case-
insensitivity, `evaluate_version` averaging, `compare_versions`
improved/unchanged).

## Limitations
- **`str.format`-style templates only** — no conditionals, loops, or
  partials (a real templating language). This is deliberate: the
  platform's zero-dependency-by-default rule rules out a third-party
  templating engine for what most prompts actually need (variable
  substitution). A caller needing real control flow composes multiple
  `PromptVersion`s in Python rather than templating logic into one
  string.
- **Two scorers today** — `exact_match_scorer` and
  `keyword_presence_scorer` are real and useful for deterministic or
  keyword-bearing prompts, but neither judges semantic quality. That's
  explicitly Phase 11's job (CONTRACT.md §4), not silently promised
  here.

## Future Roadmap
- Richer `Scorer` implementations once Phase 11's evaluation-factory
  ships (semantic similarity, LLM-graded scoring, full regression
  suites as CI gates).
- A `templates/prompts/<name>/` on-disk format so a `PromptRegistry` can
  be loaded from committed files rather than only built in Python —
  tracked, not started (see `templates/README.md`).
