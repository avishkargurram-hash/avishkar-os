# Security Framework — Contract

Language-agnostic contract for the Security Framework. The Python
reference implementation is `avishkar_security`
(`factories/security-factory/python/`).

## §0. Scope: what's automatable vs. what needs human judgment

Some of STANDARDS.md §6's requirements are mechanically checkable
today (no committed secret matching a known pattern); others
genuinely need human judgment per module ("is rate limiting configured
appropriately for this specific external system?"). This framework
does both, honestly kept separate: real, automated scanning
(`scanners.py`) for what's checkable by pattern matching, and a
structured self-assessment checklist (`checklist.py`/`review.py`) for
what isn't — never presenting a human-judgment item as if it were
automatically verified.

## §1. Secret scanning

`scan_for_secrets(text) -> Tuple[SecretMatch, ...]` — regex-based
detection of common committed-secret shapes (AWS access key IDs,
Anthropic-style API keys, generic `api_key = "..."` assignments,
PEM private key headers, bearer tokens). `SecretMatch(pattern_name,
start, end, preview)` — `preview` is a redacted excerpt (first 6 /
last 4 characters), **never the full matched text** — a security tool
that logs the very secrets it finds in full would be self-defeating.

`redact_secrets(text) -> str` replaces every match span with
`[REDACTED:pattern_name]`.

`scan_repository_for_secrets(root_dir, extensions=(...),
exclude_dirs=(...)) -> Tuple[Tuple[Path, SecretMatch], ...]` — walks a
real directory tree and scans every matching file. This is the
mechanism behind this phase's "retroactive review of everything built
above" responsibility — run for real against this repository as part
of this framework's own example, not asserted without evidence.

## §2. Checklist

`SECURITY_CHECKLIST: Tuple[ChecklistItem, ...]` — ten fixed items
drawn directly from STANDARDS.md §6 and this framework's own README
responsibilities (secrets, input validation, output filtering, rate
limiting, PII handling, approval gate for high-risk actions, timeout,
retry-amplification, least-privilege permissions, audit logging).
`ChecklistItem(id, question, why)`.

`run_checklist(subject, answers, notes={}) -> ReviewReport` —
`answers: Mapping[str, bool]` must cover every `ChecklistItem.id`
(`MissingAnswerError` otherwise) and contain no unknown ids
(`UnknownChecklistItemError` otherwise) — a checklist run that silently
skips an item is worse than one that fails loudly.
`ReviewReport.passed` is `True` only if every item passed;
`.failing` lists the failing `ChecklistResult`s.

## §3. Agent Framework guardrail bridges (`avishkar_security.agent_bridge`)

Real, reusable `avishkar_agent.Guardrail`s — pure consumers of
`agent-factory`'s already-public type (ADR-0011's dependency-direction
discipline, continued):
- `make_secret_scanning_guardrail(name=...)` — blocks a `Task` whose
  `input` matches `scan_for_secrets`.
- `make_rate_limit_guardrail(name, max_calls, window_seconds,
  clock=time.monotonic)` — a real, stateful sliding-window limiter
  (injectable clock for deterministic tests, the same DI pattern
  `mcp-factory`'s `sleep_fn` established).
- `make_input_validation_guardrail(name, validator)` — wraps a
  caller-supplied `Callable[[str], Optional[str]]` into the `Guardrail`
  shape.

## §4. Errors

`SecurityFrameworkError` (base), `MissingAnswerError`,
`UnknownChecklistItemError`.
