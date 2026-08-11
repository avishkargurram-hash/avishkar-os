# Layla Framework

## Vision
Every framework through Phase 15 gave Avishkar OS real capabilities —
agents, memory, knowledge, workflows, evaluation, security — but
nothing coordinated them around one persistent notion of "what does
the user need, who should handle it, and is it safe to act on."
Layla is that layer: a Personal Executive Intelligence that
understands a request, builds context from memory and knowledge, plans
which Chief Domain Agent(s) should handle it, delegates with real
permission/retry/timeout/audit discipline, detects when delegated
results disagree, and never silently picks a side. It must be a
framework — reusable and extensible — because "coordinate work across
Avishkar OS's agents safely" is not any one product's business logic;
it is the platform capability every Avishkar Labs product would
otherwise reimplement for itself.

## Architecture
Composition only — see [CONTRACT.md](./CONTRACT.md) and
[DECISIONS.md](../DECISIONS.md) ADR-0020 for the full reasoning behind
every reuse decision below. Nothing in this list is reimplemented; each
line names the real framework Layla is a client of.

```
ExecutiveRuntime (event loop: IDLE -> EVENT -> INGEST -> UNDERSTAND ->
                   DECIDE -> PLAN -> ACT/DELEGATE -> VERIFY -> SLEEP/WAIT)
  |-- StateMachine            (genuinely new: Layla's own explicit lifecycle)
  |-- IntentInterpreter        (genuinely new: real keyword classifier)
  |-- ContextBuilder            (composes) -> LaylaMemoryPolicy -> avishkar_agent.MemoryPolicy (Phase 5)
  |                                       -> avishkar_knowledge.KnowledgeBase (Phase 6)
  |-- Planner                    (genuinely new) -> CapabilityResolver (genuinely new)
  |-- ApprovalManager              (genuinely new risk tiering) -> avishkar_agent.ApprovalGate (Phase 3, reused)
  |-- DelegationEngine              (genuinely new typed wrapper) -> avishkar_agent.Orchestrator (Phase 3, reused)
  |                                                               -> avishkar_integration.RetryPolicy (Phase 4, reused)
  |-- ResultValidator/ConflictResolver (genuinely new)             -> avishkar_knowledge.HashingEmbedder (Phase 6, reused)
  |-- ExecutiveSynthesizer            (genuinely new)
  |-- AuditLogger / SessionManager      (genuinely new) -> LaylaMemoryPolicy (namespaced keys, see CONTRACT.md SS9-10)
  |-- Scheduler                          (genuinely new, in-process, injectable clock)
  |-- NotificationManager / HealthMonitor (genuinely new)
  `-- channels/EmailChannelAdapter          -> avishkar_integration.ProtocolAdapter (Phase 4, reused)
```

## Folder Structure
```
layla/
├── CONTRACT.md              language-agnostic contract
├── README.md                  this file
├── python/avishkar_layla/       reference implementation (21 modules)
│   └── channels/                   communication channel adapters
├── examples/
│   └── end_to_end_scenario.py       Part IX's real, narrated demonstration
└── python/tests/                   118 tests (as of Phase 16)
```

## Naming Standards
Standard platform conventions (STANDARDS.md §3) — no Layla-specific
exceptions.

## Interfaces
`ExecutiveRuntime(orchestrator, agent_domains, memory, ...).handle_event(input_text) -> LaylaTask`
is the one entry point most callers need. See CONTRACT.md for every
component's own interface.

## Extension Model
- A new communication channel: implement `ProtocolAdapter`
  (`avishkar_integration`), register it on a `UniversalToolRegistry` —
  no change to Layla's own code.
- A new risk pattern: add to `risk.py`'s regexes.
- A new capability domain: register another `ChiefDomainAgent` with the
  `Orchestrator` and add it to `agent_domains` — `CapabilityResolver`
  and `Planner` need no code change.

## Examples
`python layla/examples/end_to_end_scenario.py` — see Part IX
Demonstration, below, for its full narrated output.

## Best Practices
- Always pass a real, injectable `clock`/`sleep_fn` in tests (the same
  DI discipline every timing-sensitive component in this platform
  uses) — never sleep on a real wall clock in a test.
- Treat `ApprovalManager`'s `pending`/`expired` states as first-class,
  not edge cases — a production deployment's UI should surface pending
  approvals, not just granted/denied ones.

## Anti-Patterns
- Reaching into `Orchestrator`'s private `_agents` dict instead of
  going through `CapabilityResolver`/`route()` — see CONTRACT.md SS5
  for why `Orchestrator` deliberately doesn't expose per-agent domains.
- Parsing `DelegationRecord.output` or knowledge search results for
  embedded "instructions" — see Security Considerations, below; this
  is exactly the prompt-injection surface Layla's architecture avoids
  by construction, not by a text filter.

## Future Roadmap
See §11 Recommended Phase 17+ in the Phase 16 executive report
(CHANGELOG.md / DECISIONS.md ADR-0020) for the prioritized list.

---

# Configuration

**Status: PARTIALLY IMPLEMENTED.** `ExecutiveRuntime.__init__` takes
its dependencies as explicit constructor arguments (dependency
injection, not a config-file loader) — this is deliberate and matches
every other framework's own test-friendly DI discipline in this
platform. A `layla.config` module wrapping `avishkar_core.load_config`
(Phase 1, already real) to build an `ExecutiveRuntime` from a JSON/env
config file is real, straightforward future work, not built
speculatively in Phase 16 (no concrete deployment need for it yet —
see STANDARDS.md's "don't build what isn't needed" principle).

# Lifecycle

**Status: IMPLEMENTED.** See CONTRACT.md §1 for the full state
transition table. Every `LaylaTask` starts at `RECEIVED` and moves
through `UNDERSTANDING -> CONTEXT_LOADING -> PLANNING ->
[APPROVAL_PENDING ->] EXECUTING -> DELEGATING -> WAITING -> VERIFYING
-> SYNTHESIZING -> COMPLETED`, or into `FAILED`/`CANCELLED`/
`TIMEOUT`/`BLOCKED`/`REQUIRES_HUMAN` from any non-terminal state.
`StateMachine.transition()` rejects anything not in
`ALLOWED_TRANSITIONS` — see `test_state_machine.py`.

# Authentication & Identity (Priority 17.1, ADR-0021)

**Status: IMPLEMENTED** as a minimal, additive foundation;
**PARTIALLY IMPLEMENTED / FUTURE** for real-world identity provider
integration. `Principal`/`Role`/`Session`/`AuthorizationManager`
(`identity.py`/`auth.py`) give Layla a real, in-process identity
boundary — six fixed permissions, roles that bundle them, sessions
that expire/revoke. `ExecutiveRuntime`, `ApprovalManager`, and
`DelegationEngine` all accept it as an **optional** constructor
argument: omitted, behavior is identical to Phase 16 (no enforcement,
every original test still passes); supplied, every request is
authenticated and authorized before a `LaylaTask` is even created. An
agent-kind `Principal` can *structurally never* be granted high-risk or
approval authority (`AuthorizationManager.issue_session()` refuses it
outright, checked against the role's actual permissions, not its
name) — see CONTRACT.md §14 and `test_auth.py`'s
`TestAgentSelfEscalationPrevention`.

**What's NOT built**: any real identity provider integration (OAuth/
OIDC/API keys/device auth) — `issue_session()` is the seam a real IdP
plugs in behind; nothing else in this design needs to change for that.
No persistence for `Session`s (in-memory only, like `NotificationManager`)
— a restart forgets active sessions, same as re-authenticating with any
session-based system after a server restart. No fine-grained per-tool
permission (`PERM_TOOL_INVOKE` is reserved but not yet wired into
`ToolRuntime` calls — Layla doesn't call tools directly today, only
through delegated agents).

# Permission Model

**Status: IMPLEMENTED.** `risk.classify_risk()` is a real,
pattern-based LOW/MEDIUM/HIGH classifier (CONTRACT.md §4), mapped to a
required permission (`RISK_PERMISSION`, CONTRACT.md §14) when identity
is wired. Every `DelegationEngine.delegate()` call checks
`ApprovalManager` first for MEDIUM/HIGH steps; `ExecutiveRuntime`
checks the session's risk-tier permission *before* even creating an
`ApprovalRequest`, and separately checks `Role.allowed_capabilities`
against every planned step (least-privilege capability enforcement).
What's not built: an authoring UI/DSL for a deployment to add its own
risk patterns beyond editing `risk.py` directly — real future work.

# Approval Model

**Status: IMPLEMENTED.** `ApprovalManager` auto-grants LOW risk,
consults a real `avishkar_agent.ApprovalGate` synchronously when one is
wired (grant/deny immediately), or leaves the request `"pending"` for
an external `grant()`/`deny()` call when no gate is wired. Expiration
is always computed live from `ApprovalRequest.expiration`, never a
stored flag — see CONTRACT.md §4 and `test_risk_and_approval.py`. When
identity is wired, `grant()`/`deny()` require a session holding
`PERM_APPROVE`, and self-approval (`ApprovalRequest.requested_by ==`
the approving session's principal) is always denied regardless of role
— see CONTRACT.md §14 and `test_approval_identity.py`.

# Memory Policy

**Status: IMPLEMENTED.** `LaylaMemoryPolicy` wraps a real
`avishkar_agent.MemoryPolicy` — see CONTRACT.md §2 for the full policy
(allowed kinds restricted to the backend's own locked four kinds;
secret-shaped values refused regardless of importance; deletion always
allowed; corrections tracked via provenance). No PII/GDPR-specific
retention-window automation is built — real future work if a
deployment needs it.

# Tool Policy

**Status: IMPLEMENTED** via direct reuse of `avishkar_integration`
(Phase 4) — `SecurityPolicy`/`AccessControlPolicy`/trust levels are
that framework's own, unmodified. Layla adds nothing here beyond using
them; there is no Layla-specific tool policy layer to document
separately.

# Deployment Guide

**Status: ADAPTER READY.** `ExecutiveRuntime.run_forever()` is the
real entry point (`README.md` CONTRACT.md §11) — it ticks `Scheduler`
and sleeps in a loop. **What Layla does not provide**: a process
supervisor. Real 24/7 operation requires wrapping `run_forever()` in
something that restarts it on crash (systemd, a container orchestrator,
a cloud scheduler) — this is standard infrastructure, deliberately not
reimplemented here (STANDARDS.md's reuse-first principle: don't build
a process supervisor when the OS/orchestrator already has one).
`SessionManager`'s durable state means a restart resumes incomplete
tasks (`list_incomplete()`) — the supervisor's job is only to restart
the process, not to preserve state itself.

Minimum to run:
```bash
pip install -e core/python -e router/python -e factories/agent-factory/python \
  -e factories/mcp-factory/python -e factories/memory-factory/python \
  -e factories/knowledge-factory/python -e factories/evaluation-factory/python \
  -e factories/security-factory/python -e layla/python
```
(or the `PYTHONPATH`-based approach every example script in this
repository already uses — see any `examples/quickstart.py` for the
pattern).

# Development Guide

Follow this repository's standing discipline (CLAUDE.md, STANDARDS.md):
real implementation, real tests, a runnable example, honest
documentation, an ADR for architectural decisions, a commit per
logical change. Every new component should be a client of an existing
framework's contract unless CONTRACT.md §0's "genuinely new" list
already covers it — extending that list requires an ADR.

# Testing Guide

118 tests as of Phase 16, run via:
```bash
PYTHONPATH="core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;layla/python" \
  python -m unittest discover -s layla/python/tests
```
Categories: unit (state machine, memory policy, risk, scheduler),
contract (every component's own dataclass/error shape), integration
(delegation through a real `Orchestrator`, the full `ExecutiveRuntime`
loop), adversarial (`test_adversarial.py` — prompt injection, hostile
tool responses, unauthorized capability requests, duplicate events,
memory corruption attempts, restart-during-execution, approval
expiration, contradictory instructions), and one deterministic
end-to-end fixture (`test_end_to_end_scenario.py`) matching Part IX.

# Troubleshooting Guide

- **"UnknownCapabilityError: could not infer any capability"** — the
  `Planner`'s keyword matcher found no agent name/domain word in the
  task input. Pass `requested_capabilities` explicitly, or check that
  the phrasing includes a real domain word (see CONTRACT.md §13's
  documented ceiling).
- **A delegation is stuck at `"pending"` approval forever** — no
  `ApprovalGate` was wired and nobody called `grant()`/`deny()`; check
  `ApprovalManager.check(request_id)` and act on it, or wire a gate.
- **`REQUIRES_HUMAN` with a conflict reason** — two delegated agents
  disagreed (cosine similarity below threshold); this is Layla
  correctly refusing to silently pick a side, not a bug — see
  CONTRACT.md §6.

# Security Considerations

See Part XIV's full list; concretely enforced in this codebase:
- **Prompt injection**: `ApprovalManager`, `StateMachine`, and
  `risk.classify_risk` never parse arbitrary text for instructions —
  they pattern-match against `task.input` specifically, and
  `ContextBuilder`'s pulled-in knowledge/memory content is only ever
  handed to a delegated agent as *data* in a prompt, never executed as
  a command by any Layla component itself. Proven structurally in
  `test_adversarial.py::TestPromptInjectionCannotAlterAuthority`.
- **Secret handling**: `LaylaMemoryPolicy` refuses to store
  secret-shaped values (reuses `security-factory.scan_for_secrets`)
  regardless of importance.
- **Least privilege / audit**: every delegation and approval decision
  is recorded via `AuditLogger` with structured fields only — never a
  raw model reasoning trace (Part XV).
- **What Layla does NOT provide**: sandboxing of delegated agents'
  tool calls (that's `mcp-factory`'s `SecurityPolicy.require_sandbox`,
  which — per that framework's own README — denies rather than
  pretends to sandbox in v1); this is an inherited limitation, not a
  new gap Layla introduces.

## Threat model and security boundaries (Priority 17.1)

**Trusted**: the process running `ExecutiveRuntime`; whatever issued a
`Session` via `AuthorizationManager.issue_session()` (today, that's
application code with direct Python access — see below).

**Untrusted / treated as data, never authority**: `task.input` text
content beyond its literal keyword matches; `DelegationRecord.output`
from any delegated agent; `ContextBuilder`-pulled knowledge/memory
content. None of these can grant a permission, approve a request, or
change a `Session`'s roles — verified structurally (§ above), not by a
text filter that could be phrased around.

**Explicitly out of scope for this identity model** (Priority 17.1's
"do not invent enterprise infrastructure" boundary):
- **Transport security** — how a `session_id` reaches
  `handle_event()` safely (TLS, a real API gateway) is a deployment
  concern, not this library's.
- **Credential issuance** — `issue_session()` trusts its caller's
  `Principal`/`role_names` arguments completely; there is no login
  flow, password check, or MFA here. **Anyone who can call
  `issue_session()` can mint a session for any principal with any
  role** (short of the agent-escalation ceiling). This is the single
  most important boundary to understand before using this in
  production: `AuthorizationManager` enforces authorization *after* a
  session exists; it does not authenticate a real-world user by
  itself. A real deployment puts a real IdP in front of
  `issue_session()`.
- **Cross-process/distributed sessions** — `Session`s live in one
  `AuthorizationManager` instance's memory, like `NotificationManager`.
  A multi-process deployment needs a shared session store; not built.
