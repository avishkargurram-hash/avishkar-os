# Avishkar OS — Forensic Audit (Phases 1–16)

**Date:** 2026-08-10 · **Auditor:** the same agent that built the
platform, auditing its own work — see "On this audit's own limits" at
the end before trusting any score here uncritically.

## Methodology

Per Part XII of the Phase 16 directive, this audit did not re-read
READMEs and accept their claims. Concrete checks actually run, with
evidence:

1. **Repo-wide grep for placeholder markers** — `TODO`/`FIXME`/`XXX`/
   `HACK` across every `.py` file outside `__pycache__`. Result: zero
   unfinished-work markers. The only hits are (a) a scaffold generator
   that *emits* the string `"TODO"` into a *new agent's* generated
   README template — a feature, not unfinished code — and (b)
   `software-ai-engineering`'s own `static_check` tool, which *detects*
   TODO/FIXME in code it's reviewing.
2. **Repo-wide grep for stub function bodies** (`def ...:` immediately
   followed by a bare `pass`) — zero matches.
3. **Repo-wide grep for `NotImplementedError` and bare `except:`** —
   zero matches. Every exception handler is either typed or an
   explicit `except Exception as exc:` with a `# noqa` explaining why
   the broad catch is deliberate (isolation boundaries: `EventBus`
   handler isolation, `ToolRuntime` normalizing adapter failures,
   `WorkflowEngine` retry loops).
4. **Duplicate-abstraction grep** — `RetryPolicy`, `ApprovalGate`,
   `MemoryPolicy`, `Tool`, `QualityGate`, `Guardrail` each have exactly
   **one** class definition in the entire repository, confirmed by
   grep, not by trusting each framework's own "we reused it" claim.
5. **Dependency-direction check** — `core/` and `router/` import zero
   `avishkar_*` packages (router's `avishkar_core` import is inside a
   documented `try/except ImportError` graceful-degradation block, not
   absent). No `factories/*` package imports a specific `agents/*`
   module; the only such import anywhere is `layla/examples/`, which
   is expected (an example demonstrating composition).
6. **Repo-wide secret scan** — ran `security-factory`'s own
   `scan_repository_for_secrets()` against the entire repository (not
   a subset). 25 pattern matches, **100% traced to well-known-fake
   fixtures** (AWS's own public documentation placeholder
   `AKIAIOSFODNN7EXAMPLE`, and synthetic `sk-ant-FAKE...`/`Bearer
   EXAMPLE...` strings in test files proving detection works). Zero
   real secrets. `.gitignore` correctly excludes `.env`/`.env.*`/
   `*.key`; no `.env` file is tracked.
7. **External-boundary test-reality check** — confirmed `AnthropicProvider`
   (the one real LLM provider implementation) is tested exclusively via
   a `client=` dependency-injection seam against `MagicMock`/a fake
   client, **never a live network call**. This is true of every
   external boundary in this repository (see Finding SEC-1, below) —
   stated plainly here because it materially changes how much
   confidence "661 tests passing" should inspire about production
   readiness against real external systems.
8. **Full regression run** — every package's test suite executed
   individually with its exact documented `PYTHONPATH`, immediately
   before this audit was written: **661 tests, 0 failures** (382
   factories/frameworks, 9 Knowledge Library modules, 151 across 11
   Chief Domain Agents, 119 Layla).
9. **Scale** — 11,440 lines of non-test Python, 6,968 lines of test
   Python, 27 commits, 16 phases, 11 Chief Domain Agents, 1 Layla.

## Per-phase scorecard

Scores are `/10`. A framework that does exactly what it honestly
claims to do, with real tests and a documented, non-fabricated gap
list, can and does score well here — the bar is **honesty and
real-code-behind-the-claim**, not feature completeness against an
imagined ideal. Where a framework's own README already documents a
limitation, that limitation is reflected in the score, not treated as
a fresh discovery.

| Phase | Architecture | Implementation | Testing | Security | Reliability | Observability | Documentation | Prod. Readiness |
|---|---|---|---|---|---|---|---|---|
| 1. Core Engine | 9 | 9 | 9 | 8 | 8 | 6 | 9 | 7 |
| 2. AI Router | 8 | 8 | 8 | 7 | 7 | 6 | 8 | 6 |
| 3. Agent Framework | 9 | 9 | 9 | 7 | 7 | 6 | 9 | 6 |
| 4. Universal Integration/MCP | 8 | 7 | 8 | 6 | 6 | 6 | 8 | 5 |
| 5. Memory | 8 | 8 | 8 | 7 | 7 | 5 | 8 | 6 |
| 6. Knowledge | 7 | 6 | 8 | 7 | 7 | 5 | 8 | 5 |
| 7. Workflow | 8 | 7 | 8 | 6 | 6 | 5 | 8 | 5 |
| 8. Prompt | 7 | 7 | 8 | 7 | 7 | 4 | 8 | 5 |
| 9. Template | 7 | 7 | 8 | 7 | 7 | 4 | 8 | 5 |
| 10. Starter Kit | 7 | 7 | 7 | 6 | 6 | 4 | 8 | 4 |
| 11. Evaluation | 6 | 6 | 8 | 6 | 6 | 4 | 8 | 4 |
| 12. Security | 7 | 7 | 9 | 6* | 7 | 5 | 9 | 5 |
| 13. Chief Domain Agents (11) | 8 | 8 | 8 | 6 | 6 | 5 | 9 | 5 |
| 14. Knowledge Library | 7 | 7 | 7 | 6 | 6 | 4 | 7 | 4 |
| 15. Final Integration | 7 | 7 | 6 | 6 | 6 | 5 | 8 | 5 |
| 16. Layla | 8 | 8 | 8 | 6 | 6 | 5 | 8 | 4 |

\* `security-factory` scores 6/10 on its *own* Security axis
deliberately — a secret scanner and risk-tiering layer are real
security *tooling*, but the framework itself has never been
red-teamed, and its pattern library is small by design (see Finding
SEC-2).

**Reading the pattern:** Testing scores are consistently the platform's
strongest axis (7–9 across the board) because every phase's own
example was actually executed, not just written, and real bugs were
caught this way in nearly every phase (documented per-phase in
`CHANGELOG.md`). Observability and Production Readiness are
consistently the weakest — this is accurate, not modesty: there is no
metrics dashboard, no distributed tracing, no CI/CD pipeline, no
containerization, and no deployment ever performed. See Findings,
below.

## Security audit findings

| ID | Severity | Finding |
|---|---|---|
| SEC-1 | **HIGH** | **No test in this repository has ever made a real network call to a live external system** — not to Anthropic's API, not to an MCP server, not to a REST endpoint, not to an email provider. Every external boundary (`AnthropicProvider`, `MCPAdapter`, `RESTAdapter`, `EmailChannelAdapter`) is tested via dependency-injected fakes. This is good testing *hygiene* (deterministic, no live credentials needed) but means **zero evidence exists that this platform's assumptions about any real external API's actual behavior are correct.** The first real deployment against a live provider is genuinely untested territory. |
| SEC-2 | **MEDIUM** | `security-factory`'s secret scanner is pattern-based against five known shapes (AWS keys, Anthropic-style keys, PEM headers, generic bearer tokens, `api_key=` assignments). A secret in any other shape (a database connection string, a JWT, a custom-format internal token) would not be caught. Documented honestly in that framework's own README; still a real gap. |
| SEC-3 | **MEDIUM** | **No authentication/authorization model exists anywhere in this platform.** There is no user-identity concept, no session/token verification, no RBAC. `ApprovalGate`/`ApprovalManager` gate *actions* by risk tier, but nothing verifies *who* is initiating a request in the first place. Any caller with code-level access to a `ChiefDomainAgent` or `ExecutiveRuntime` can act as any "user." This is appropriate for a platform library (auth is typically a product concern layered on top), but it means **this platform provides zero auth primitives a product could reuse** — every product built on Avishkar OS must build its own, with no guidance from this repository. |
| SEC-4 | **MEDIUM** | `mcp-factory`'s `SecurityPolicy.require_sandbox=True` **denies** execution rather than actually sandboxing (an explicit, documented v1 choice — "denies rather than pretends to sandbox," per that framework's own CONTRACT.md). Correct engineering honesty, but it means **no untrusted tool can currently run at all** in this platform — a real capability gap, not just a documentation gap. |
| SEC-5 | **LOW** | `DelegationEngine`'s timeout enforcement (Layla) is a post-hoc elapsed-time check, not preemptive — a genuinely hung call blocks the calling thread for its full real duration before the timeout is even detected. Documented in `layla/CONTRACT.md` §5. |
| SEC-6 | **LOW** | No secrets-manager integration (Vault, AWS Secrets Manager, etc.) — the platform's convention is `.env`/environment variables only (`core/`'s `Config` layering). Adequate for the current stage; a real production deployment handling live credentials should not stop here. |
| SEC-7 | **INFORMATIONAL** | Prompt-injection resistance for Layla is structural (verified by test: `ApprovalManager`/`StateMachine`/`risk.classify_risk` never parse arbitrary text for instructions) but this property has **not been adversarially tested against a real model actually generating text that tries to exploit it** — the adversarial tests use hand-crafted injected strings against Layla's own Python logic, not a live model in the loop. |
| — | — | **Zero CRITICAL findings.** No committed secrets, no SQL/command injection surface found (no raw SQL string interpolation anywhere; `SQLiteMemoryPolicy` uses parameterized queries throughout), no path traversal found in file-writing code (`template-factory`'s `instantiate()`, `memory-factory`'s `FileMemoryPolicy` both write under caller-supplied root directories without further path validation — worth a defensive `resolve()`-and-`is_relative_to()` check before this handles untrusted paths in production, tracked as SEC-8 below). |
| SEC-8 | **LOW** | `FileMemoryPolicy`/`template-factory.instantiate()` do not validate that a `key`/`relative_path` stays within the intended root directory (no defense against a caller-supplied `"../../etc/passwd"`-style key). Not exploitable today because every caller in this repository supplies trusted, code-level keys — but it's a real gap if either component is ever exposed to externally-supplied keys. |

## Reliability audit findings

- **Retries are real but synchronous/blocking** — every retry loop in
  this platform (`workflow-factory`'s `WorkflowEngine`, `mcp-factory`'s
  `ToolRuntime`, `security-factory`'s rate limiter, `layla`'s
  `DelegationEngine`) uses an injectable `sleep_fn` for testability,
  but the *production* default is `time.sleep`, which blocks the
  calling thread. There is no async/concurrent retry path anywhere in
  this platform. For a single-user assistant this is likely fine; for
  a multi-tenant deployment it is a real scaling constraint.
- **No circuit breakers** — a persistently failing external dependency
  (a down MCP server, a rate-limited model provider) will be retried
  according to each component's own `RetryPolicy`, but nothing tracks
  cross-call failure rates to open a circuit and stop hammering a
  known-down dependency. `mcp-factory`'s `MetricsCollector` tracks
  error rates but nothing *acts* on them automatically.
- **Idempotency**: `SQLiteMemoryPolicy.remember()` uses `INSERT ...
  ON CONFLICT DO UPDATE` — genuinely idempotent by key. `Layla`'s
  `SessionManager.save()` is idempotent (same key, overwrite semantics).
  `DelegationEngine`'s retries are **not** idempotent-safe by
  construction — if a delegated `ChiefDomainAgent` call has any
  side effect beyond returning text (none currently do, but a future
  agent tool that e.g. sends an email would), a retried call after a
  timeout could double-execute that side effect. No idempotency-key
  mechanism exists to prevent this. Real gap, not yet exercised because
  no current tool has an external side effect.
- **Crash recovery**: genuinely proven for `Layla`'s `SessionManager`
  (real cross-process test: save via one `FileMemoryPolicy` instance,
  load via a brand-new instance pointed at the same directory,
  `list_incomplete()` recovers the task). **Not proven** for anything
  mid-*delegation* — if a process crashes while a `DelegationEngine`
  call is in flight, the task is persisted at `DELEGATING` state on
  resume, but nothing automatically re-drives it; a caller must notice
  and call `handle_event()` again (which starts a *new* task, not a
  resumption of the old plan — `Layla` has no "resume this exact plan"
  entry point yet).
- **Concurrency**: no component in this platform is tested under
  concurrent access. `EventBus`, `UniversalToolRegistry`,
  `NotificationManager`, `Scheduler` all use plain Python data
  structures with no locking. Single-threaded, single-process use is
  safe (every test assumes this); concurrent use from multiple threads
  is untested and likely unsafe for at least `EventBus._subscribers`
  and `Scheduler._heap` (both mutated without synchronization).

## Integration audit findings

Per Part XVI's explicit instruction not to accept "integration exists
because an import succeeds," every integration claim below was
verified by an **executed runtime path**, not an import check:

- Core + Router + Agent + Memory + Knowledge + Evaluation + Security,
  composed in one real agent (`medical-healthcare`, Phase 13) — proven
  by that agent's own 16 passing tests plus its runnable example.
- Universal Integration (a real `RESTAdapter` call through
  `UniversalToolRegistry`/`ToolRuntime`) + Agent Framework, composed in
  one workflow — proven by `docs/final-integration-verify.py`'s actual
  captured output (Phase 15).
- Workflow + two real Chief Domain Agents (`legal-compliance` +
  `finance-economics`), composed and synthesized — proven by
  `workflows/cross-domain-review`'s runnable example (Phase 14).
- Layla + real `Orchestrator` + real `research-intelligence` agent +
  real `KnowledgeBase` + real `ProjectStore`, composed end to end
  through all nine `LaylaTask` lifecycle states — proven by
  `layla/examples/end_to_end_scenario.py`'s actual captured output.
- **Not verified**: Layla + a *live* email send (adapter-ready only,
  no transport wired); Layla + `langgraph-factory`/`n8n-factory`
  (both still deferred, ADR-0009); any two-region/multi-process
  deployment of any component.

## Performance / cost findings

- **Token usage**: every `Router.route()` call tracks `cost_usd` via
  `CostTracker` (real, per-caller accumulation) — genuinely measurable,
  not fabricated. But because every test uses `MockProvider` with
  `input_cost_per_mtok=0.0`, **no real cost data has ever been
  generated** by this test suite; the mechanism is real, the numbers
  it would report on a live deployment are unverified.
- **Unnecessary model calls**: `ChiefDomainAgent.handle()`'s
  plan-act-reflect loop can run up to `blueprint.max_iterations` model
  calls per task even when the first iteration's output would have
  passed every quality gate on inspection — no early-exit heuristic
  beyond "did the gates pass," which is correct behavior, not waste.
  `Layla`'s own components (`IntentInterpreter`, `risk.classify_risk`,
  `CapabilityResolver`) are pure Python/regex — **zero model calls**,
  which is a genuine cost win worth highlighting: routing and risk
  decisions cost nothing before a single delegated agent call happens.
- **Retrieval quality vs. cost tradeoff**: `HashingEmbedder`
  (`knowledge-factory`) is stdlib-only and free to run, at the
  documented cost of crude ranking quality on common-word-heavy
  queries — a deliberate, honest tradeoff, not an oversight.

## Code quality findings

- **Naming/typing**: consistent `snake_case` modules, `PascalCase`
  classes, type hints throughout (verified by spot-reading; no
  systematic type-checker like `mypy` was run as part of this audit —
  real gap, tracked in Recommended Phase 17+).
- **No dead code found** by the grep sweep in Methodology.
- **No circular dependencies found** — the dependency-direction check
  above confirms `core/`/`router/` have zero platform dependencies, and
  every later framework's `pyproject.toml` dependency list matches
  what it actually imports (spot-checked for `layla/`, `evaluation-
  factory`, `starter-kit-factory`).
- **Test quality**: consistently uses dependency injection (`clock=`,
  `sleep_fn=`, `client=`, `transport=`) rather than monkeypatching or
  real waits/network calls — a genuinely good, consistent pattern
  across all 27 commits, not just claimed.

## Critical remaining work

1. **Run this platform against at least one live external system once**
   (a real Anthropic API call with a real key, in a controlled test) —
   closes SEC-1, the single largest gap between "tested" and "proven."
2. **A resume-in-place entry point for Layla** — `SessionManager`
   recovers task *state* after a restart, but nothing re-drives a
   `DELEGATING`-state task automatically; today a caller must notice
   and re-submit.
3. **An idempotency-key mechanism for `DelegationEngine`** before any
   delegated tool has a real external side effect (the moment
   `EmailChannelAdapter` gets a real transport, this becomes urgent).
4. **A concurrency review** of `EventBus`, `UniversalToolRegistry`,
   `Scheduler` before any multi-threaded deployment.
5. **A real auth/identity layer decision** — even if it's explicitly
   "out of scope, each product builds its own," that should be a
   recorded ADR, not silence.

## Recommended Phase 17+

1. Run a real, credentialed integration test against the live
   Anthropic API (behind a flag, never in default CI) — the highest-
   value single test this platform is missing.
2. `langgraph-factory`/`n8n-factory`/`project-factory`/
   `documentation-factory` — still deferred per ADR-0009; schedule via
   ADR when a real need appears.
3. A twelfth Chief Domain Agent only if a genuine new domain need
   appears (requires its own ADR, ADR-0007's roster lock).
4. A named-product starter kit once an actual product (Tryvanta,
   Humanify OS, etc.) is ready to build on Avishkar OS (ADR-0016's
   deferred item).
5. Layla: config-file loader (`layla.config`), a resume-in-place API,
   a real communication-channel transport (email/Slack) behind actual
   credentials, concurrent `delegate_team()`/`broadcast()`.

## On this audit's own limits

This audit was performed by the same agent that wrote the code being
audited, in the same session, using automated greps and re-running the
existing test suite — not an independent reviewer, not a red team, and
not a check against a real adversary. Every score above should be read
as "the honest self-assessment of a careful author," which is a real
and useful signal (especially the concrete, evidenced findings in
Methodology) but is not a substitute for independent security review
or a live-fire production incident before this platform is trusted
with real user data, real credentials, or real financial/legal actions.
