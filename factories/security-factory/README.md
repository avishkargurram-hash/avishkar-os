# Security Framework

## Vision
STANDARDS.md §6 has said since the very first commit that every MCP
server and agent tool goes through a guardrail/threat-model checklist
before it's "reusable" — until this phase, that was aspirational.
Security Framework makes it real: automated secret scanning where
pattern matching genuinely works, a structured checklist for what
needs human judgment, and real guardrails `agent-factory` can use
today, not bolt on later.

## Architecture
```
factories/security-factory/python/avishkar_security/
├── scanners.py         scan_for_secrets / redact_secrets / scan_repository_for_secrets
├── checklist.py          SECURITY_CHECKLIST -- 10 fixed items from STANDARDS.md SS6
├── review.py               run_checklist() -> ReviewReport
└── agent_bridge.py           make_secret_scanning_guardrail / make_rate_limit_guardrail / make_input_validation_guardrail
```
See [CONTRACT.md](./CONTRACT.md) §0 for the explicit split between
what's automated and what's a structured self-assessment — this
framework never presents a human-judgment item as machine-verified.

## Interfaces
`scan_for_secrets(text) -> Tuple[SecretMatch, ...]`. `redact_secrets(text)
-> str`. `scan_repository_for_secrets(root_dir) ->
Tuple[RepositoryFinding, ...]`. `run_checklist(subject, answers, notes=
{}) -> ReviewReport`. `make_secret_scanning_guardrail()` /
`make_rate_limit_guardrail(name, max_calls, window_seconds)` /
`make_input_validation_guardrail(name, validator)` — all return real
`avishkar_agent.Guardrail`s.

## Folder Structure / Naming Standards
See tree above; [STANDARDS.md](../../STANDARDS.md) §3.

## Extension Model
A new secret pattern is one entry in `scanners._PATTERNS`. A new
checklist item is one `ChecklistItem` appended to `SECURITY_CHECKLIST`
— every existing `run_checklist()` caller then gets
`MissingAnswerError` until they answer it, by design (a silently
optional new checklist item defeats the point).

## Examples
`python factories/security-factory/examples/quickstart.py` — scans and
redacts a secret-shaped string, blocks a real `ChiefDomainAgent`'s task
via `make_secret_scanning_guardrail()`, runs a checklist review with a
deliberate failure, and — the "retroactive review" responsibility —
**actually scans this entire repository** for committed secrets. As of
this phase's own run: the only matches anywhere in the repo are this
very example's own demo string (AWS's public documentation placeholder,
`AKIAIOSFODNN7EXAMPLE`); zero real findings.

## Best Practices
- Prefer `scan_repository_for_secrets()` in CI over a one-off manual
  check — it's the same real function this framework's own example
  runs against itself.
- Give every `run_checklist()` failure a `note` explaining the plan,
  not just `False` — `ReviewReport.failing` is meant to be read by a
  human deciding whether to ship anyway.

## Anti-Patterns
- Storing a `SecretMatch`'s full matched text anywhere (logs, reports,
  commit messages) — always use `.preview` (redacted) instead; see
  CONTRACT.md §1.
- Treating a passing `scan_for_secrets()` result as proof a module has
  no secrets — it proves no *known pattern* matched; see Limitations.
- Answering every checklist item `True` without actually checking —
  `run_checklist()` can't detect a dishonest self-assessment; the
  value is in the structure, not an illusion of automation it doesn't
  have.

## Testing Strategy
24 tests: every scanner pattern (using well-known-fake fixtures — AWS's
own public `AKIAIOSFODNN7EXAMPLE` placeholder, and clearly-marked
`EXAMPLE`/`FAKE` strings for the others — never a realistic-looking
secret), redaction (single and multiple matches, spans stay correct
when redacting back-to-front), `scan_repository_for_secrets` (finds a
real planted secret, respects `exclude_dirs`/`extensions`),
`run_checklist` (pass/fail, missing-answer and unknown-item errors),
and all three guardrails (secret blocking, a real sliding-window rate
limiter with an injectable clock, input validation wrapping).

## Limitations
- **Pattern-based scanning only** — `scan_for_secrets` catches known
  secret *shapes* (AWS keys, Anthropic-style keys, PEM headers, generic
  bearer tokens/API-key assignments). It cannot catch a secret in a
  format it doesn't recognize, a secret split across lines, or one
  disguised (base64-wrapped, etc.). It's a real, useful first line of
  defense, not a complete solution — a human security review still
  matters for anything high-stakes.
- **`run_checklist()` is a structured self-assessment, not an
  automated auditor** — for the seven items that aren't secret-related,
  it records what a human (or agent) asserts, and can't verify the
  assertion is true. See CONTRACT.md §0 for why this split is explicit
  rather than papered over.
- **`make_rate_limit_guardrail` is in-process and per-instance** — its
  state (`call_times`) isn't shared across multiple agent instances or
  processes; a real multi-instance deployment needs a shared store
  (e.g. via `memory-factory`), tracked as future work.

## Future Roadmap
- A CI job running `scan_repository_for_secrets()` on every PR,
  blocking merge on a real finding (README.md's original Future
  improvements note, now a concrete, buildable next step).
- A distributed rate limiter backed by `memory-factory`'s
  `SQLiteMemoryPolicy`/`FileMemoryPolicy` for multi-instance deployments.
- Additional secret patterns as new provider integrations are added
  (a new model provider's key format, a new cloud provider's
  credential shape).
