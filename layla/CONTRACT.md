# Layla — Language-Agnostic Contract

Layla is Avishkar OS's Personal Executive Intelligence layer — see
[DECISIONS.md](../DECISIONS.md) ADR-0020 for why it is a new top-level
platform capability, not a Chief Domain Agent or a factory, and why
every capability domain below is a **client** of an existing
framework's contract, never a reimplementation. Python ships first
(`python/avishkar_layla/`) as the reference implementation, per the
same pattern `core/`/`router/` established (ADR-0008).

## §0. What Layla is not

Layla holds no domain expertise and performs no reasoning about a
task's actual subject matter — that is every Chief Domain Agent's job
(`agent-factory`, Phase 3). Layla decides *whether* an action needs
approval, *who* should handle a request, and *how* multiple results
combine — it is a coordination and policy layer, not an eleventh (or
twelfth) domain agent.

## §1. State

A `LaylaTask` moves through an explicit, finite state machine:

```
RECEIVED -> UNDERSTANDING -> CONTEXT_LOADING -> PLANNING
  -> [APPROVAL_PENDING ->] EXECUTING -> [DELEGATING -> WAITING ->]
  -> VERIFYING -> SYNTHESIZING -> COMPLETED
```

Terminal/exception states, reachable from any non-terminal state:
`FAILED`, `CANCELLED`, `TIMEOUT`, `BLOCKED`, `REQUIRES_HUMAN`.

`StateMachine.transition(task, new_state) -> LaylaTask` validates the
transition against a fixed adjacency table (`ALLOWED_TRANSITIONS`) and
raises `InvalidTransitionError` for anything not explicitly listed —
an implicit "any state can go anywhere" machine is not a state
machine. Every transition is recorded (`LaylaTask.history`) for
audit (§9).

## §2. Memory

`LaylaMemoryPolicy` wraps a real `avishkar_agent.MemoryPolicy`
(`memory-factory`, Phase 5) — it is not a second memory system.
**`kind` is passed straight through to the wrapped backend and is
therefore restricted to exactly the four kinds every real
`MemoryPolicy` implementation enforces** (`short_term`, `long_term`,
`episodic`, `semantic` — a real constraint discovered by reading
`memory-factory`'s actual backend code, not assumed): a call with any
other `kind` raises the backend's own `InvalidMemoryKindError`, not a
Layla-specific error. Components that need finer-grained categories
than four (the audit trail, session state, the project store) use a
**namespaced key** within the appropriate kind (`episodic` for the
audit trail, `long_term` for session/project state) rather than
inventing new kinds the backend would reject — see §9/§10/§3. Every
stored value is a `MemoryRecord(value, confidence, provenance,
importance, stored_at, kind)`:

- `remember(kind, key, value, *, confidence=1.0, provenance="user",
  importance="normal") -> None` — raises `MemoryPolicyViolationError`
  if `kind` is not in the policy's `allowed_kinds`, or if any string
  content within `value` (recursively, through nested dicts/lists)
  matches `security-factory.scan_for_secrets` (reused, not a new
  detector) — a secret-shaped value is refused regardless of
  `importance`; there is no importance level that makes storing a
  credential acceptable.
- `recall(kind, key) -> Optional[MemoryRecord]`
- `forget(kind, key) -> None` — always allowed; user control over
  deletion is unconditional (§0 of `memory-factory`'s own design never
  makes forgetting a policy decision, and Layla doesn't either).
- `correct(kind, key, new_value, *, reason) -> MemoryRecord` — a
  correction is a new `remember()` with `provenance="correction:
  {reason}"`, keeping the old value's history inspectable via the
  underlying backend rather than silently overwritten.

## §3. Project model

`Project(id, name, objectives, milestones, tasks, decisions, owners,
status, dependencies)` — deliberately generic; no product is named in
code (ADR-0020, and consistent with `starter-kit-factory`'s ADR-0016
precedent against hardcoding named products). `ProjectStore` persists
`Project`s through the same `MemoryPolicy` §2 wraps, under `kind=
"long_term"` with keys namespaced `project:{project_id}` — one storage
mechanism, not two.

## §4. Risk classification and approval

`classify_risk(action_description, action_kind) -> RiskLevel` (`LOW` |
`MEDIUM` | `HIGH`) — a real, pattern-based classifier (the same
honestly-scoped-heuristic discipline every Chief Domain Agent's own
tools use — see e.g. `medical-healthcare`'s `flag_urgency`), not a
model call, so risk classification is deterministic and auditable.

`ApprovalManager.request(task, risk_level) -> ApprovalRequest` — for
`LOW`, auto-grants (`ApprovalRequest.status = "granted"`,
`auto=True`). For `MEDIUM`/`HIGH`, creates a pending request; the
actual gating mechanism is `avishkar_agent.ApprovalGate` (reused
directly, not reimplemented — ADR-0011 §7's precedent). An
`ApprovalRequest` carries `expiration`; `ApprovalManager.check(id) ->
str` returns `"pending"`, `"granted"`, `"denied"`, or `"expired"` (the
last computed from `expiration`, not a stored flag that can drift).

## §5. Delegation

`DelegationEngine` wraps a real `avishkar_agent.Orchestrator` instance
(constructed by the caller, e.g. via `agents/orchestrator`'s
`build_executive_orchestrator()`, Phase 13) — actual dispatch is
`orchestrator.route(Task(input=..., task_type=plan_step
.required_capability))`, Phase 3's own matching logic
(`Orchestrator._match_one`: exact name, else domain substring),
**not reimplemented**. `CapabilityResolver.match(plan_step) ->
Tuple[str, ...]` is a separate, small, real matcher used only for
*inspection before dispatch* (so a `Planner` can validate a capability
has at least one candidate before building a step around it) — it
applies the same policy (exact name or domain substring) but is built
from an explicit `{agent_name: domain}` mapping the caller supplies,
since `Orchestrator.list_agents()` returns names only and does not
expose per-agent domains publicly. `DelegationEngine.delegate(plan_step) ->
DelegationRecord` — every delegation is typed (`PlanStep` in,
`DelegationRecord` out), inspectable (`DelegationRecord.status`,
`.attempts`, `.started_at`, `.completed_at`), auditable (published via
`avishkar_core.EventBus`), permission-aware (checked against
`ApprovalManager` first for `MEDIUM`/`HIGH` risk steps), retryable
(`RetryPolicy` reused from `avishkar_integration`, third framework to
reuse it after `workflow-factory`), and timeout-aware (`timeout_seconds`
enforced as an elapsed-time check after the call returns — Python has
no safe preemptive cross-platform timeout without a subprocess/thread
boundary this contract does not require; see README.md Limitations for
why this is a documented, honest boundary, not silently ignored).

## §6. Planning and synthesis

`Planner.plan(task, context) -> Plan` — `Plan(steps: Tuple[PlanStep,
...])`, `PlanStep(id, required_capability, input, depends_on)`. A real
capability-matching planner (keyword/domain matching over the
`CapabilityResolver`, §5), not a model call — deterministic, testable,
and honestly scoped (see README.md Limitations for its keyword-match
ceiling, the same limitation every rule-based classifier in this
platform documents about itself).

`ResultValidator.validate(results) -> ValidationReport` — checks every
`DelegationRecord.status == "completed"`.
`ConflictResolver.detect(results) -> Tuple[Conflict, ...]` — flags
disagreement using `evaluation-factory`'s scoring primitives (reused,
not reimplemented): two results scored against the same
`weighted_keyword_scorer` diverging past a threshold is a conflict.
`ExecutiveSynthesizer.synthesize(results, conflicts) -> str` — refuses
to silently pick a side when `conflicts` is non-empty and no
resolution strategy was given (raises `UnresolvedConflictError`),
matching Part V's "do not silently choose an answer when confidence is
insufficient."

## §7. Scheduling

`Scheduler` — a real, in-process, min-heap-backed scheduler.
`schedule_once(at, callback) -> ScheduledJobId`,
`schedule_recurring(interval_seconds, callback, *, start_at=None) ->
ScheduledJobId`, `cancel(job_id) -> bool`, `tick(now) -> Tuple[JobId,
...]` — DI'd clock (`clock: Callable[[], float]`, the same seam
`security-factory`'s rate limiter and `mcp-factory`'s retry backoff
already use), so scheduling logic is deterministically testable
without real wall-clock waits. **`Scheduler` does not itself run a
background thread/process** — `ExecutiveRuntime.run_forever()` (§9) is
the caller responsible for repeatedly invoking `tick()`; real 24/7
operation requires an external process supervisor (see README.md
Deployment).

## §8. Notifications and monitoring

`Notification(severity, message, source, created_at)` — severity one
of `INFO`, `WARNING`, `ACTION_REQUIRED`, `CRITICAL`.
`NotificationManager.notify(...)` queues; `.pending(min_severity=None)
-> Tuple[Notification, ...]`. `HealthMonitor.observe(signal) ->
Optional[Notification]` — classifies a real signal (an `AgentResult`
with `status="failed"`, a `DelegationRecord` timeout, an
`ApprovalRequest` expiration) into a `Notification` or `None` (nothing
worth surfacing) — never fabricates a signal.

## §9. Audit

`AuditLogger.record(event_type, payload, *, task_id=None) ->
AuditRecord` — structured, persisted through the same `MemoryPolicy`
§2 wraps, under `kind="episodic"` with keys namespaced
`audit:{task_id or "system"}:{sequence}`. **Never stores a model's raw
chain-of-thought** — only structured fields (`intent`, `plan_id`,
`delegation`, `approval`, `result_summary`) per Part XV's explicit
instruction. `AuditLogger.history(task_id) -> Tuple[AuditRecord,
...]`.

## §10. Session durability

`SessionManager` persists `LaylaTask` state through the same
`MemoryPolicy` §2 wraps, under `kind="long_term"` with keys namespaced
`session:{task.id}`; a separate `long_term` key (`session:__index__`)
holds the list of known task ids so `list_incomplete()` doesn't
require a backend that supports key enumeration (`FileMemoryPolicy`
and `InMemoryMemoryPolicy` do via `list_keys()`, but that method is not
part of the locked `MemoryPolicy` interface itself — see
`memory-factory/CONTRACT.md` — so `SessionManager` doesn't depend on
it). `SessionManager.save(task) -> None`, `.load(task_id) ->
Optional[LaylaTask]`, `.list_incomplete() -> Tuple[LaylaTask, ...]`. A
process restart followed by `SessionManager.list_incomplete()` recovers
every task not in a terminal state — verified by a real test that
constructs a fresh `SessionManager` instance against the same backing
store (the identical cross-instance-persistence proof
`legal-compliance`/`education-knowledge` already established for their
own `FileMemoryPolicy` usage in Phase 13).

## §11. Executive Runtime

`ExecutiveRuntime` composes every component above around one explicit
loop (`IDLE -> EVENT -> INGEST -> UNDERSTAND -> DECIDE -> PLAN -> ACT/
DELEGATE -> VERIFY -> SLEEP/WAIT`, Part IX): `handle_event(event) ->
LaylaTask` processes one `avishkar_core.Event` end to end (synchronous,
deterministic, testable). `run_forever(sleep_fn=time.sleep) -> None`
is a thin loop calling `Scheduler.tick()` and draining a real
`EventBus` subscription — the actual "run 24/7" entry point a
deployment's process supervisor calls; not exercised in tests as an
infinite loop (see README.md Testing Strategy for how the loop body is
tested instead).

## §12. Communication channels

A channel is a `ProtocolAdapter` (`avishkar_integration`, Phase 4),
registered on a `UniversalToolRegistry` — never a parallel "channel"
abstraction. `layla/python/avishkar_layla/channels/email_adapter.py`
ships one real, adapter-ready implementation
(`EmailChannelAdapter(ProtocolAdapter)`) with an injectable `transport`
seam (same DI pattern `RESTAdapter` already uses) — tested against a
fake transport; marked **ADAPTER READY / REQUIRES EXTERNAL
CREDENTIALS** for actual sending, not claimed as a live integration.

## §13. Intent and context

`IntentInterpreter.interpret(text) -> Intent(category, urgency,
requires_action)` — a real, pattern-based classifier (`category` one
of `"question"`/`"request"`/`"command"`/`"information"`; `urgency` one
of `"low"`/`"normal"`/`"high"`/`"urgent"`), the same honestly-scoped
heuristic discipline as `risk.classify_risk` (§4) — not a model call.

`ContextBuilder.build(task, memory, knowledge_bases=()) ->
Mapping[str, Any]` — composes relevant `MemoryRecord`s (via
`LaylaMemoryPolicy.recall`, caller-supplied keys) and
`knowledge-factory` `KnowledgeBase.search()` results (Phase 6, reused
directly) into one context mapping handed to the `Planner`. A pure
composer — it does not itself decide what's relevant beyond what the
caller asks it to look up.

## §14. Identity and authorization (Priority 17.1, ADR-0021)

`Principal(id, kind, display_name="")` — `kind` one of `"user"` /
`"agent"` / `"system"`. `Role(name, permissions, allowed_capabilities=
None)` — a fixed, small permission vocabulary
(`PERM_COMMAND`/`PERM_INVOKE_AGENT`/`PERM_INVOKE_AGENT_WRITE`/
`PERM_INVOKE_AGENT_HIGH_RISK`/`PERM_APPROVE`/`PERM_TOOL_INVOKE`), not
an open-ended RBAC string namespace. `Session(id, principal, role_names,
issued_at, expires_at=None, revoked=False)`.

`AuthorizationManager.issue_session(principal, role_names,
ttl_seconds=None) -> Session` — refuses (`EscalationDeniedError`) to
grant a role carrying `PERM_INVOKE_AGENT_HIGH_RISK` or `PERM_APPROVE`
to a `kind="agent"` `Principal`, structurally, regardless of which role
is named — an autonomous agent can never hold high-risk or approval
authority, by construction, not by convention (Priority 17.1 SS5).
`.authenticate(session_id) -> Session` (raises `UnauthenticatedError`
for unknown/revoked/expired). `.authorize(session, permission)` /
`.authorize_capability(session, capability)` (raise
`PermissionDeniedError`). `.require(session_id, permission) -> Session`
combines both.

**Integration is entirely additive** — every component above
(`ExecutiveRuntime`, `ApprovalManager`, `DelegationEngine`,
`AuditLogger`) accepts `authorization`/`session_id`/`principal_id` as
*optional* parameters. Omitted, behavior is identical to Phase 16 (no
identity enforcement). Supplied: `ExecutiveRuntime.handle_event()`
authenticates and requires `PERM_COMMAND` before a `LaylaTask` is even
created; after planning, every `PlanStep.required_capability` is
checked against the session's `allowed_capabilities` (least-privilege
capability enforcement, SS4); before an `APPROVAL_PENDING` transition,
the session must hold the risk-tier permission (`RISK_PERMISSION[risk]`)
or the task is denied without ever creating an `ApprovalRequest`;
`ApprovalManager.grant()` requires `PERM_APPROVE` and refuses
self-approval (`ApprovalRequest.requested_by == session.principal.id`
is always denied); every `AuditRecord` carries the acting
`principal_id`.

## §15. Idempotency and side-effect safety (Priority 17.2, ADR-0022)

`classify_operation(description) -> OP_READ | OP_WRITE | OP_HIGH_RISK`
— a distinct axis from `risk.classify_risk`: risk asks "how much harm
can this cause" (approval-worthiness); this asks "does retrying this
risk duplicating a real-world effect" (idempotency-worthiness). A
LOW-risk action can still be a WRITE that must never be silently
retried (e.g. "send a routine status email"). **Fail-closed default**:
text matching neither a recognized READ nor WRITE/HIGH_RISK verb is
classified `OP_WRITE`, never `OP_READ` — an unrecognized action is
treated as idempotency-sensitive until proven otherwise.

`ExecutionRecord(idempotency_key, operation_kind, description, status,
result=None, error=None, attempts=0, created_at, updated_at)`. Status
lifecycle: `REQUESTED -> AUTHORIZED -> APPROVED -> EXECUTING ->
COMPLETED`, with `REJECTED`/`CANCELLED`/`FAILED`/`EXPIRED` also
terminal. **`UNKNOWN` is deliberately excluded from
`TERMINAL_EXECUTION_STATES`** — an uncertain outcome (e.g. a timeout on
a WRITE after the provider may have already accepted it) requires an
explicit `resolve_unknown()` call, never a silent retry.

`ExecutionTracker(memory: LaylaMemoryPolicy, clock=time.time)` —
persisted through the same `LaylaMemoryPolicy` every other Layla
component uses (`kind="long_term"`, keys namespaced
`execution:{idempotency_key}`), not a second storage mechanism.
`.begin(key, operation_kind, description) -> ExecutionRecord` is
idempotent: an existing record for `key` is returned unchanged (the
caller inspects `.status`), *unless* `description` differs from the
original request for that same key, in which case it raises
`IdempotencyConflictError` — a key collision must never silently
return the wrong cached result. `.transition(key, new_status,
result=None, error=None, increment_attempts=False)`.
`.resolve_unknown(key, resolved_status, note="")` — refuses
(`ValueError`) to touch anything but a genuinely `UNKNOWN` record, so
it can never be used to silently overwrite a real `COMPLETED`/`FAILED`
outcome.

**`DelegationEngine` integration is entirely additive** —
`execution_tracker` is an *optional* constructor parameter, the same
pattern established by `approval_manager`/`authorization`. Omitted:
behavior is identical to Phase 16/17.1. Supplied: every
`delegate(plan_step, task_id, principal_id)` call is tracked under an
idempotency key of `{task_id}:{plan_step.id}`:

- An existing `COMPLETED` record short-circuits — the orchestrator is
  **never invoked again** for that key; the cached `agent_name`/`output`
  is returned directly.
- An existing record still `AUTHORIZED`/`APPROVED`/`EXECUTING`/`UNKNOWN`
  (i.e. claimed by a prior attempt that never reached a terminal state
  — whether a concurrent duplicate call or a crash mid-flight) **refuses
  to proceed** for any non-`READ` operation, fail-closed, rather than
  risk a duplicate side effect. `READ` operations are exempt — retrying
  a read never duplicates a real-world effect.
- A `timeout` on a non-`READ` step transitions the record to `UNKNOWN`,
  not `FAILED` — `FAILED` implies "safe to retry," which a timeout does
  not guarantee. A subsequent `delegate()` call for the same key is then
  refused until an explicit `resolve_unknown()`.

## §16. Errors

`LaylaError` (base), `InvalidTransitionError`,
`MemoryPolicyViolationError`, `UnknownCapabilityError`,
`DelegationTimeoutError`, `UnresolvedConflictError`,
`ApprovalExpiredError`, `ApprovalDeniedError`, `SessionNotFoundError`,
`UnauthenticatedError`, `PermissionDeniedError`, `EscalationDeniedError`,
`IdempotencyConflictError`, `UnknownExecutionOutcomeError`.
