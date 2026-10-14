# Avishkar OS / Layla — Production Readiness (Phase 17 Gate)

**Date:** 2026-08-11 · **Scope:** Phases 1–16 (audited in
`docs/phase16-forensic-audit.md`) plus Phase 17 Priorities 17.1–17.5
(this document). Read alongside that audit — this document does not
repeat its per-phase scorecards, only what changed and what the
combined system can honestly claim today.

**Standard applied**: per the Phase 17 directive's own closing
instruction — *"Do not optimize for saying 'done.' ... Be conservative
with real-world side effects. Be honest about anything that could not
actually be verified."* Every claim below is backed by a command that
was actually run and an output that was actually observed during this
work, not by inspection alone.

---

## 1. What is production-ready

- **Core Engine, AI Router (offline path), Universal Integration
  (against fakes), Agent Framework, Memory (both backends, now
  thread-safe within a process), Knowledge, Workflow, Evaluation,
  Security scanning** — unchanged from Phase 16's own assessment;
  Phase 17 did not regress any of these (verified: every framework's
  own pre-existing test suite still passes unmodified).
- **Layla's state machine, memory policy, capability resolution,
  planning, delegation-with-retry, conflict detection/synthesis,
  scheduling, audit trail, session persistence** — Phase 16 baseline,
  unchanged in behavior when Priority 17.1–17.5's new capabilities are
  omitted (every one is additive/optional; the original 119 Phase 16
  tests still pass byte-for-byte unmodified).
- **Layla's identity/authorization foundation** (Priority 17.1) — a
  real, tested, least-privilege permission model with structural
  (not naming-convention) anti-escalation for agent principals and
  enforced self-approval denial. Production-ready *as a foundation* —
  see §2 for what it does not include.
- **Layla's idempotency/side-effect-safety layer** (Priority 17.2) —
  a real `ExecutionTracker`, now proven correct under actual concurrent
  access (Priority 17.4), preventing duplicate delegation on retry/
  redelivery for any operation classified non-READ.
- **Layla's resume-in-place** (Priority 17.3) — a real, tested,
  runnable crash-recovery path (`ExecutiveRuntime.resume()`) that
  correctly skips already-completed delegation steps and re-checks a
  genuinely-persisted pending approval, verified via simulated crashes
  (fresh objects against the same on-disk store — see §4's honesty
  note on what "simulated" means here) and a runnable example.
- **Layla's concurrency guarantees** (Priority 17.4) — real, per-
  component locks closing confirmed races (not theoretical ones),
  proven with actual `threading.Thread`-based tests, not just code
  review. Single-process thread-safety is production-ready.
- **Observability plumbing for a real model provider** (Priority 17.5)
  — `Router`'s cost/latency/token tracking (real since Phase 2) plus
  the new `request_id` field are production-ready to *use*; whether
  the live path itself has been *proven* to work is a separate
  question — see §2.

## 2. What is NOT production-ready

- **Real-world identity/credential issuance.** `AuthorizationManager.
  issue_session()` trusts its caller's `Principal`/`role_names`
  arguments completely. Anyone who can call it can mint a session for
  any principal. No login flow, no MFA, no real IdP integration. A
  production deployment MUST put a real identity provider in front of
  this before exposing Layla to untrusted callers.
- **Cross-process / multi-worker deployment.** Every lock added in
  Priority 17.4 is a `threading.Lock`/`RLock` — process-local. Two
  separate OS processes (e.g. behind a load balancer, or two workers
  in a process pool) are not coordinated by anything in this codebase:
  they can race on the same `FileMemoryPolicy` directory, the same
  task id, the same approval request, with no lock preventing it. A
  single-process deployment is the only configuration these
  guarantees actually cover today.
- **Live external system behavior, empirically.** The full
  Layla→Router→AnthropicProvider→live-API path has real, complete,
  tested (via DI) code and a real, safe, ready-to-run live test — but
  that live test has never actually been executed against the real
  Anthropic API during this work (no credentials were available). Do
  not read "the code path is real" as "the code path has been proven
  to work against the live API." See §4.
- **`UniversalToolRegistry`/rate-limit enforcement** (mcp-factory) —
  declared in `ToolContract.rate_limit`, not enforced by `ToolRuntime`.
  Unrelated to Phase 17; a pre-existing Phase 4 gap, unchanged.
- **No real sandboxing of delegated agents' tool calls.**
  `SecurityPolicy(require_sandbox=True)` denies execution rather than
  isolating it (mcp-factory, Phase 4, unchanged).
- **No encryption at rest, no TTL/retention policy** for either memory
  backend (memory-factory, Phase 5, unchanged).
- **Layla's own communication channels** (`EmailChannelAdapter`) are
  "ADAPTER READY" — real code, but require external credentials
  (an SMTP/API transport) never configured or exercised live.
- **Unrestricted, autonomous Layla operation.** See §11 — this
  document does not claim Layla is safe to run with no human in the
  loop against real external systems.

## 3. What was tested

**732 tests across the entire platform, run this session, all
passing except one deliberately skipped by design:**

| Suite | Tests | Result |
|---|---|---|
| `core` | 47 | pass |
| `router` | 42 | pass |
| `factories/agent-factory` | 71 | pass |
| `factories/evaluation-factory` | 16 | pass |
| `factories/knowledge-factory` | 20 | pass |
| `factories/mcp-factory` | 70 | pass |
| `factories/memory-factory` | 24 | pass |
| `factories/prompt-factory` | 24 | pass |
| `factories/security-factory` | 24 | pass |
| `factories/starter-kit-factory` | 12 | pass |
| `factories/template-factory` | 15 | pass |
| `factories/workflow-factory` | 17 | pass |
| `layla` | 190 | 189 pass + 1 skipped (live-gated) |
| 10 Chief Domain Agents + Orchestrator | 151 | pass |
| `knowledge/platform-standards` | 4 | pass |
| `templates/framework-readme` | 2 | pass |
| `workflows/cross-domain-review` | 3 | pass |
| **Total** | **732** | **731 pass, 1 skipped, 0 failed, 0 errors** |

**Every runnable example in the repository was executed this
session** (28 `examples/quickstart.py`-style scripts plus Layla's two
narrated scenarios, `end_to_end_scenario.py` and
`crash_recovery_scenario.py`) — all exited 0. `docs/final-integration-
verify.py` (the Phase 15 cross-framework proof) was re-run and still
passes.

**Static analysis**: `flake8 --select=E9,F` (syntax errors + pyflakes)
run across every file this phase touched or added — zero syntax
errors platform-wide; a handful of pre-existing unused-import warnings
in Phase 16/17.1 files not otherwise touched this phase (see §9); the
findings in files this phase actually created or modified were fixed.
`mypy` is installed but this codebase has no `mypy.ini`/strict-typing
configuration to run it against meaningfully — not attempted as a
gate.

**Security scan**: `security-factory.scan_repository_for_secrets()`
re-run across the full, now-larger repository (post Phase 17): 26
findings, 100% traced to well-known placeholder/fixture values
(AWS's own documented example key `AKIAIOSFODNN7EXAMPLE`, synthetic
`sk-ant-...0000`/`Bearer ...fxyz` test fixtures, one instance being
`docs/phase16-forensic-audit.md`'s own prose *quoting* that AWS example
key). **Zero real secrets.** `git status` is clean — nothing untracked,
nothing staged-but-uncommitted.

## 4. What was tested against real external systems

**Nothing new was tested live during this session.** This is the same
answer the Phase 16 audit gave (SEC-1), still true after Phase 17,
stated plainly rather than implied to have changed:

- The real `AnthropicProvider` exists, is complete, and is now backed
  by a real, safe, opt-in live test
  (`layla/python/tests/test_live_anthropic_integration.py`,
  `docs/live-integration-guide.md`) — but that test was not run
  against a real API key during this work. No `ANTHROPIC_API_KEY` was
  available in the environment. The skip path itself *was* verified
  (it correctly reports `skipped`, not a fabricated `ok`).
- "Resume-in-place" and "crash recovery" were verified via the
  established pattern this codebase already used before Phase 17 (
  `test_session.py`'s cross-instance persistence proof): constructing
  fresh Python objects against the same on-disk `FileMemoryPolicy`
  store, simulating what a real process restart would look like at the
  object-instantiation level. **This is not the same as killing and
  restarting an actual OS process.** It proves the persisted-state
  contract is correct; it does not prove behavior under a real SIGKILL,
  OS-level file-handle interruption, or partial-write corruption.
- No real email was sent, no real Slack/webhook fired, no real
  financial or destructive operation of any kind was performed by any
  test, example, or script run during this entire Phase 17 effort.

## 5. What remains mocked

Everything not listed in §4. Concretely: every agent's model calls
(`MockProvider`), every tool/MCP/REST call
(`avishkar_integration`'s fake transports/sessions), every approval
gate not explicitly wired to a real human decision process, and (with
the one described exception) every AI Router call in this platform's
732 tests and 28 examples.

## 6. What credentials are required (for what)

| Credential | Required for | Where it's read from |
|---|---|---|
| `ANTHROPIC_API_KEY` | The one live integration test (§4); any real deployment using `AnthropicProvider` | Environment variable only — never hardcoded, never logged, never committed (verified: §3's secret scan) |
| `LIVE_TEST_MODE=1` | Opting the live test in at all (not a credential, but required alongside the key) | Environment variable |
| An SMTP/email-API transport | `EmailChannelAdapter` (ADAPTER READY, not exercised live) | Would be constructor-injected `transport=`; none configured today |
| A real identity provider | Real user authentication in front of `issue_session()` (§2) | Not built; this is the seam it plugs into |

No credential of any kind is required to run the full 732-test suite,
every example, or `docs/final-integration-verify.py` — all offline.

## 7. What security controls exist

- **Least-privilege capability enforcement** (Priority 17.1):
  `Role.allowed_capabilities` checked against every planned step before
  delegation.
- **Structural anti-escalation**: an agent-kind `Principal` can never
  be issued `PERM_INVOKE_AGENT_HIGH_RISK`/`PERM_APPROVE`, checked
  against the role's actual permission set, not its name.
- **Self-approval always denied**, regardless of role.
- **Fail-closed idempotency classification**: unrecognized operation
  text defaults to `WRITE` (idempotency-sensitive), never `READ`.
- **Fail-closed concurrency guards**: an in-flight or uncertain
  non-READ operation refuses a concurrent/duplicate retry rather than
  guessing it's safe.
- **Secret-shaped value refusal** in `LaylaMemoryPolicy.remember()`
  (reuses `security-factory.scan_for_secrets`).
- **Prompt-injection resistance is structural**: external content
  (knowledge search results, delegated-agent output) is only ever data
  in a prompt, never parsed as an instruction by any Layla component
  itself — proven by `test_adversarial.py`, unchanged this phase.
- **Complete audit trail**: every state transition, delegation, and
  approval decision recorded via `AuditLogger`, now itself race-free
  under concurrent writes (Priority 17.4).
- **No committed secrets** (§3, re-verified after Phase 17's
  additions).
- **Least-privilege data model choices**: `IdempotencyConflictError`
  refuses a key-collision reuse rather than silently returning a wrong
  cached result; `resolve_unknown()` refuses to touch anything but a
  genuinely `UNKNOWN` record.

## 8. Known limitations (consolidated from every priority's own README section)

- No real IdP; `issue_session()` trusts its caller (§2).
- No cross-process/multi-worker coordination (§2) — locks are
  process-local.
- `FileMemoryPolicy`/`SQLiteMemoryPolicy` have no OS-level file locking
  for true multi-process safety, only in-process thread-safety.
- Idempotency tracking covers the Layla→Agent delegation seam only,
  not a delegated agent's own direct tool calls (would require a
  `mcp-factory`, Phase 4, change — out of scope, not silently claimed).
- No automatic resolution of `UNKNOWN` execution outcomes —
  `resolve_unknown()` is deliberately manual.
- No sub-step-granularity resume for `UNDERSTANDING`/`CONTEXT_LOADING`/
  `PLANNING` — unnecessary, since those phases do no I/O (§3 of
  CONTRACT.md's resume section explains why).
- No automatic re-driving of a `REQUIRES_HUMAN` task once a human acts
  — a deployment's own code must call `resume()` (or lower-level APIs)
  after the decision.
- `UniversalToolRegistry`/rate-limit enforcement not deeply audited for
  concurrency beyond `MetricsCollector` (Priority 17.4 §, mcp-factory).
- No real sandboxing of delegated tool calls (mcp-factory, unchanged).
- The live integration path (§4) is real but unexercised against the
  actual API in this work.
- A handful of pre-existing `flake8` unused-import findings remain in
  files not touched this phase: `layla/python/avishkar_layla/
  identity.py`, `layla/python/tests/test_adversarial.py`,
  `test_approval_identity.py`, `test_runtime_identity.py`, and
  `layla/examples/end_to_end_scenario.py` (all Phase 16/17.1,
  cosmetic, non-blocking).

## 9. Deployment infrastructure required

- A process supervisor (systemd, a container orchestrator, a cloud
  scheduler) to restart `ExecutiveRuntime.run_forever()` on crash and
  call `resume()` on every task `sessions.list_incomplete()` returns at
  startup — Layla does not supply this itself (by design, per
  STANDARDS.md's reuse-first principle).
- A durable `memory=` backing store at a **stable path** — a
  `FileMemoryPolicy`/`SQLiteMemoryPolicy` pointed at ephemeral
  container storage defeats resume-in-place entirely; this must be a
  persistent volume or equivalent.
- If using the live Anthropic path: `ANTHROPIC_API_KEY` provisioned via
  the deployment's own secrets manager, never baked into an image or
  committed config.
- If real-world identity is needed: a real IdP integrated in front of
  `AuthorizationManager.issue_session()` (§2) — not built here.
- If multi-worker/horizontal scaling is needed: an external
  coordination layer (distributed lock, single-writer process, or a
  real database with row-level locking) — not built here (§2).

## 10. Remaining risks

- **Highest**: deploying with multiple worker processes/replicas
  sharing one `FileMemoryPolicy` directory or one logical task
  namespace without external coordination — the concurrency
  guarantees in this document are process-local only.
- **High**: exposing `issue_session()` (directly or via a thin wrapper)
  to any caller without a real authentication layer in front of it —
  by design, it trusts its arguments.
- **Medium**: relying on the live Anthropic integration path in
  production before it has ever actually been exercised against the
  real API — the code is real and reviewed, but "reviewed" is not
  "observed working."
- **Medium**: a deployment that never restarts the process supervisor
  or never calls `resume()` on startup effectively has no crash
  recovery despite the underlying persistence being correct — the
  guarantee requires the deployment to actually use it.
- **Low**: the remaining pre-existing gaps in §8 (rate limiting,
  sandboxing, encryption at rest) — real but long-documented,
  unchanged by this phase, not newly introduced risk.

## 11. What must be completed before unrestricted Layla autonomy

In priority order:
1. **A real identity provider** in front of session issuance — today,
   anything with code-level access to `AuthorizationManager` can act as
   any principal.
2. **A real, executed live-integration run** against the Anthropic API
   (or whichever provider a deployment uses) — proving the reviewed
   code path actually behaves as expected against the real service,
   not just against its documented shapes.
3. **Cross-process/multi-worker coordination** if the deployment will
   ever run more than one process against shared state — otherwise,
   run single-process only.
4. **A real communication channel** actually configured and tested
   (email/Slack/etc.) if Layla is expected to communicate externally —
   `EmailChannelAdapter` is ADAPTER READY, not yet exercised live.
5. **A deliberate decision about approval-gate policy** for MEDIUM/HIGH
   risk actions in production — today, "no gate wired" means an
   action genuinely waits in `APPROVAL_PENDING` until a human calls
   `grant()`/`deny()`; a production deployment needs to decide who that
   human is and how they're notified (`NotificationManager` exists;
   wiring it to a real paging/alerting system does not).
6. Only after 1–5: consider narrowing the human-in-the-loop surface
   for specific, well-understood, LOW-risk, read-only task categories —
   never as a blanket removal of approval gates.

---

*This document is Phase 17's production-readiness gate. It supersedes
no prior audit; it is additive context on top of
`docs/phase16-forensic-audit.md`. Re-verify §3/§4's claims by actually
running the commands in `docs/live-integration-guide.md` and this
repository's own test suites before trusting this document's claims
secondhand.*
