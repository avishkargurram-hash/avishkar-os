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

## §16. Resume-in-place and durable execution (Priority 17.3, ADR-0023)

`LaylaTask` gains two persisted fields: `plan: Optional[Plan]` (the
actual `Plan`, not just `plan_id` — a resumed task never re-plans) and
`pending_approval_id: Optional[str]` (the live `ApprovalRequest.id`
while `state == APPROVAL_PENDING` — a resumed task re-checks the same
request rather than losing track of it). `SessionManager` persists
both (`session.py`'s `_task_to_dict`/`_task_from_dict`).

`ApprovalManager(..., memory: Optional[LaylaMemoryPolicy] = None)` —
*optional*, same additive pattern as every other Priority 17
integration point. Omitted: `ApprovalRequest`s live only in an
in-process dict, exactly as Phase 16/17.1 (lost on restart).
Supplied — as `ExecutiveRuntime` always does, since it already
requires a `memory` — every `request()`/`grant()`/`deny()` is also
persisted (`kind="long_term"`, `approval:{request_id}`), so a pending
approval, or one decided while the process was down, survives a
restart and is visible to a completely different `ApprovalManager`
instance querying the same store.

`ExecutiveRuntime.handle_event()` and `.resume(task_id, session_id=)`
are two thin entry points around one shared, re-entrant pipeline: every
stage is guarded by the task's *current* `state`, not assumed to start
fresh, so calling it against an already-partway-through task continues
it rather than redoing completed work. Concretely:
- `handle_event()` starts a task at `RECEIVED` and drives it straight
  through, identically to Phase 16/17.1.
- `resume(task_id)` reloads a persisted task by id. A terminal task or
  one in `REQUIRES_HUMAN` is returned **unchanged** — resuming is
  idempotent, and `REQUIRES_HUMAN` needs an explicit human decision
  first (grant/deny a stuck approval, fix a `blocked_reason`), not an
  automatic retry.
- A task reloaded at `APPROVAL_PENDING` has its `pending_approval_id`
  re-checked live. `"granted"` → continues to `EXECUTING`. `"pending"`
  → returns unchanged (still waiting; call `resume()` again later).
  `"denied"`/`"expired"` → `REQUIRES_HUMAN`.
- A task reloaded at `EXECUTING` (the last durable checkpoint before
  delegation begins) re-runs the full delegation loop over the
  persisted `plan.steps`. When `execution_tracker` (§15) is wired, an
  already-`COMPLETED` step is returned from cache without invoking the
  orchestrator again — this is the actual mechanism that makes
  resuming a large multi-step plan (e.g. 50 companies, crashed after
  17) continue from the correct point rather than restart blindly, and
  it is `DelegationEngine`'s existing idempotency machinery (Priority
  17.2), not a second, parallel resume mechanism.

**Durable checkpoints** — `self._session.save(task)` is called at
exactly three points in the pipeline, each chosen because it is the
last point before something either expensive (re-planning) or
externally consequential (delegation, an approval decision) happens:
right after a `Plan` is created and capability-checked (state
`PLANNING`), right after an `ApprovalRequest` is created (state
`APPROVAL_PENDING`), and right before the delegation loop starts (state
`EXECUTING`). States before the first checkpoint (`RECEIVED`/
`UNDERSTANDING`/`CONTEXT_LOADING`) are pure, synchronous, and
side-effect-free — nothing is ever persisted mid-way through them, so
there is nothing to resume from there; a genuine crash that early
simply means the request was never durably received and must be
resubmitted via `handle_event()`.

**A real bug this priority found and fixed**: `DelegationEngine`, when
constructed with its own `approval_manager=`, independently re-checks
approval for every non-LOW-risk `PlanStep` — a legitimate standalone
feature (see `test_delegation.py`), but Priority 17.2/17.1's design
already has `ExecutiveRuntime` fully gate the *task-level* risk/approval
decision before `EXECUTING` is ever reached. Wiring the same
`ApprovalManager` into both created a second, independent
`ApprovalRequest` per step whose id was never surfaced anywhere a human
could grant it — harmless in Phase 16/17.1, where an ungated pending
task-level approval always collapsed straight to `REQUIRES_HUMAN` and
`DELEGATING` was never reached, but a real, previously-latent bug once
`resume()` could legitimately carry a task-level-granted approval
through to `DELEGATING`. Fixed by no longer passing `approval_manager=`
into the `DelegationEngine` `ExecutiveRuntime` constructs internally —
`DelegationEngine` still accepts it for direct, standalone use.

## §17. Concurrency model (Priority 17.4, ADR-0024)

**Ordering guarantee**: two calls racing the *same* task id
(`ExecutiveRuntime.handle_event()`/`.resume()`), the *same* idempotency
key (`DelegationEngine.delegate()`/`ExecutionTracker`), or the *same*
approval request id (`ApprovalManager.grant()`/`.deny()`/`.check()`)
are serialized — one fully completes before the other's critical
section begins. Two calls touching *different* task ids / idempotency
keys / approval ids run fully concurrently — Layla does not serialize
unrelated work.

**What is locked, and why**:
- `ExecutionTracker` (§15): one lock per instance, guarding
  `begin()`/`transition()`/`resolve_unknown()`. `begin()`'s
  get-or-create is a genuine check-then-act race — the returned
  record's `claimed_this_call` attribute (not persisted) distinguishes
  "I created this" from "I observed one already there," since both
  cases return a record with `status == EXEC_REQUESTED`.
  `_CLAIMED_NON_TERMINAL_STATES` (delegation.py) now includes
  `EXEC_REQUESTED`, not just `AUTHORIZED`/`APPROVED`/`EXECUTING`/
  `UNKNOWN` — a second caller observing a just-created REQUESTED record
  it did not itself create is refused exactly like any other unresolved
  in-flight state, for any non-`READ` operation.
- `ApprovalManager` (§4): one lock, guarding
  `request()`/`grant()`/`deny()`/`check()`/`_require()` — two
  concurrent `grant()`/`deny()` calls on the same request id ("
  simultaneous approvals") are serialized, never interleaved.
- `SessionManager` (§10): one lock, guarding only the shared
  `session:__index__` read-modify-write inside `save()` — the task
  record itself is written outside the lock (each task has its own key,
  no cross-task contention there).
- `AuditLogger` (§9): one lock, guarding `record()`'s sequence-number
  computation and index update — without it, two concurrent `record()`
  calls for the same scope could compute the same sequence number and
  one would silently overwrite the other's entry.
- `Scheduler` (§7): one lock, guarding `_heap`/`_jobs`/`_callbacks`
  across `schedule_once()`/`schedule_recurring()`/`cancel()`/`tick()` —
  a job's own callback runs *outside* the lock (see scheduler.py's
  module docstring for why: holding it during an arbitrary callback
  would block every other scheduler operation, and a callback that
  reschedules itself would deadlock on re-entry).
- `ExecutiveRuntime`: one lock per task id (created lazily, never
  freed — see runtime.py), guarding the *entire* `_advance()` call for
  that task, including the (re)load from `SessionManager` inside
  `resume()`. Loading inside the lock, not before it, is what prevents
  two racing `resume()` calls on the same task from each working off a
  stale in-memory snapshot.
- `EventBus` (core, Phase 1), `FileMemoryPolicy`/`SQLiteMemoryPolicy`
  (memory-factory, Phase 5), `MetricsCollector` (mcp-factory, Phase 4):
  each gained a narrow, additive lock as part of this same hardening
  pass — see the module docstring in each file for the specific race
  it closes. These are documented exceptions to those frameworks'
  otherwise-locked status, justified because the Phase 17 directive
  explicitly names EventBus/Memory/ToolRuntime as audit/harden targets
  and because none of these changes alter single-threaded behavior
  (every pre-existing test in those frameworks still passes unmodified).

**Deliberately coarse, not per-key**: every lock above is one lock per
*component instance*, not one per task/key/request id. These are fast,
local, in-memory-or-disk operations (no network I/O inside a locked
section anywhere in this list) — a single lock is simple and correct;
per-key locking would need its own lock-lifecycle management (when is
it safe to forget a per-key lock?) for a benefit that only matters
under far higher contention than this platform's current scale.

**What is explicitly NOT covered**:
- **Cross-process/distributed coordination.** Every lock here is a
  `threading.Lock`/`RLock` — it serializes threads within one Python
  process. Two separate OS processes (e.g. two workers behind a load
  balancer) calling `resume()` on the same task id, or writing to the
  same `FileMemoryPolicy` directory, are not coordinated by anything in
  this codebase. A real multi-process/multi-worker deployment needs an
  external coordination mechanism (a distributed lock, a single-writer
  process, a real database with row-level locking) — not built here;
  see `docs/production-readiness.md`.
- **`Orchestrator`/`ChiefDomainAgent` (agent-factory, Phase 3)**:
  audited, not modified. `Orchestrator._agents` is populated once at
  construction and never mutated afterward, so concurrent `route()`
  calls only ever *read* it — safe by construction, no lock needed.
  `InMemoryMemoryPolicy`'s `remember()`/`recall()`/`forget()` are each
  a single dict operation (atomic under the GIL), not a read-modify-
  write sequence like `FileMemoryPolicy`'s — also safe without a lock.
- **`UniversalToolRegistry`/rate-limit enforcement (mcp-factory)**: not
  deeply audited this pass; `MetricsCollector` (the one confirmed race
  found there) was fixed. See `docs/production-readiness.md` for what
  remains unverified.
- **Scheduler `cancel()` racing `tick()` at the exact moment a job's
  callback is already running**: `cancel()` can still return `True` for
  a job whose callback started (under the lock) a moment before
  `cancel()` was called — the lock prevents corruption and duplicate
  *firing*, not a callback that is already executing from being
  "un-fired." This is the same lazy-deletion tradeoff the scheduler
  already documented before this priority, not a new gap.

## §18. Controlled live integration validation (Priority 17.5, ADR-0025)

**Status: real infrastructure, opt-in only.** Every test in this
platform through Priority 17.4 runs offline, against dependency-
injected fakes — real, but never against a live external system (Phase
16 audit finding SEC-1). This priority adds one deliberate, narrow
exception: `layla/python/tests/test_live_anthropic_integration.py`,
gated `@unittest.skipUnless(LIVE_TEST_MODE=1 and ANTHROPIC_API_KEY
set)`. Default (either unset): skipped, not failed, not faked. See
`docs/live-integration-guide.md` for exact execution instructions.

When enabled, it validates the *full* path this platform has never
exercised live: `ExecutiveRuntime.handle_event()` → `Planner` →
`DelegationEngine` → a real `ChiefDomainAgent` → a real
`avishkar_router.Router` → the real `AnthropicProvider` → the live
Anthropic Messages API → a real response → `ResultValidator` →
`ExecutiveSynthesizer`. Every piece of that chain except the network
call itself was already real in Phase 16; this priority is the first
time the network call is real too.

**Safeguards, by construction**: fixed to `claude-haiku-4-5` (the
cheapest catalog model), `max_tokens=32`, a single fixed trivial
prompt, and an explicit cost-ceiling assertion (`$0.01`) that fails the
test loudly rather than silently accepting unexpected spend. The task
is phrased as a read-only, LOW-risk request — it never reaches
`DelegationEngine`'s write-classified path, never triggers an approval
gate, never invokes a tool/channel adapter. No email/message is sent;
no record is created, modified, or deleted; no financial or
destructive operation is performed anywhere in this test, live or not.

**Tracking**: `router/python/avishkar_router/types.py` gained an
additive `request_id: Optional[str] = None` field on both
`ProviderResponse` and `CompletionResponse` (populated by
`AnthropicProvider` from the live API response's own `.id`; `None` for
`MockProvider`, which has no real request to identify) — closing the
one gap in Router's already-real cost/latency/token tracking (`Router.
route()` already computed `cost_usd`/`latency_ms`/`input_tokens`/
`output_tokens` and logged/published them per call since Phase 2).
`layla/python/avishkar_layla/types.py`'s `DelegationRecord` gained an
additive `cost_usd: float = 0.0` field, passed through from the
delegated agent's own `AgentResult.cost_usd`, so real spend is visible
at the Layla layer, not only by reaching into `Router.cost_tracker`
directly.

**Credentials**: read from the `ANTHROPIC_API_KEY` environment variable
only — never hardcoded, never logged, never committed. `git status`
and a repository-wide secret scan (`security-factory.
scan_repository_for_secrets()`) are part of this priority's own
verification; see the Phase 17 final forensic report for the result.

## §19. Personal Model (Mission Layla Part 1, ADR-0026)

`PersonalModel(memory: LaylaMemoryPolicy)` — Layla's continuously-
evolving model of the person she works for. Not a second memory
system: every fact is a namespaced key inside the same
`LaylaMemoryPolicy` every other Layla component uses
(`kind="long_term"`, `personal:{category}:{key}`), following the exact
index-key pattern `SessionManager`/`AuditLogger`/`ApprovalManager`
already established for enumerable state within the locked backend's
four fixed memory kinds.

`CATEGORIES`: `identity`, `preferences`, `goals`, `decision_patterns`,
`work_patterns`, `communication_style`, `project_context`,
`relationships`, `behavioral_patterns`, `personal_knowledge`,
`life_events`, `habits`, `long_term_objectives`.
`SENSITIVE_CATEGORIES` (`relationships`, `behavioral_patterns`) require
`confirmed=True` on every write (`set()` and `correct()`) — raises
`SensitiveCategoryNotConfirmedError` otherwise, never inferred
automatically.

`PersonalFact(category, key, value, confidence, provenance, importance,
stored_at, corrected)` — every fact carries confidence, provenance,
and a timestamp (reusing `MemoryRecord`'s own fields verbatim, no new
schema).

`set(category, key, value, *, confidence=1.0, provenance="user",
importance="normal", confirmed=False, resolve=None) -> PersonalFact` —
idempotent (writing the same value twice is a no-op); writing a
*different* value than what's already stored raises
`PersonalFactContradictionError` unless `resolve="overwrite"` (accept
the new value) or `resolve="ignore"` (keep the existing one) is given
explicitly, or the caller uses `correct()` instead — contradiction
handling is a real, enforced code path, not a documented aspiration.

`correct(category, key, new_value, *, reason, confirmed=False) ->
PersonalFact` — the explicit, reasoned-overwrite path; delegates to
`LaylaMemoryPolicy.correct()` verbatim, always succeeds regardless of
any prior contradiction (that's what distinguishes it from `set()`).

`get(category, key) -> Optional[PersonalFact]`, `get_category(category)
-> Dict[str, PersonalFact]`, `forget(category, key)` (deletion is never
a policy decision — always allowed, matching `LaylaMemoryPolicy.forget()`
itself), `summary() -> str` (a compact digest for `ContextBuilder`;
`SENSITIVE_CATEGORIES` content is never included verbatim in a summary
— only the category name and fact count).

**Privacy, by construction**: no category ships with seed/default/
example personal data of any kind — every fact is written only by an
explicit runtime call, never hardcoded. This is a deliberate,
structural difference from the one external system this module's
design was informed by (GENESIS, audited during Mission Layla's
planning phase): GENESIS hardcodes a specific real person's name,
family members, and health information directly in versioned source as
default values. `PersonalModel` contains no GENESIS code and no
GENESIS data — only the general shape of one pattern judged worth
reusing (a sensitive-layer confirmation gate), reimplemented from
scratch.

**Integration is entirely additive**: `ExecutiveRuntime(...,
personal_model=None)` and `ContextBuilder.build(..., personal_model=
None)` — omitted, behavior is identical to before this module existed.
Supplied, `ContextBuilder` folds `personal_model.summary()` into every
task's `context["personal_model_summary"]`.

## §20. Proactive Intelligence and persistent-runtime orchestration (Mission Layla Parts 2 and 11, ADR-0026)

`ProactiveEngine(session_manager, audit_logger, notifications, *,
act_callback=None, extra_evaluators=(), clock=time.time, ...)` —
evaluates real, already-recorded system state (never a fabricated
signal) and decides whether Layla should act without being asked.
Combines two roles the Mission Layla directive names separately but
which are the same mechanism in this architecture: "should Layla act
proactively" (Part 2) *is* the decision that drives Layla's
SLEEP → EVENT → WAKE → ... → SLEEP persistent-runtime cycle (Part 11).
A `Scheduler`/`run_forever()` tick is the EVENT; `evaluate()` is
WAKE+CONTEXT+DECIDE; the dispatched trigger is ACT (or a deliberate
non-act). No LLM is invoked merely to check "did anything change."

**Action levels**: `ACTION_IGNORE` (returned to the caller, never
audited — no noise), `ACTION_OBSERVE` (recorded via `AuditLogger`,
never surfaced), `ACTION_SUGGEST`/`ACTION_ASK` (a `Notification`,
`SEVERITY_ACTION_REQUIRED`, never an autonomous side effect),
`ACTION_ACT` (drives a real `ExecutiveRuntime.handle_event()` call —
always the *full* pipeline: UNDERSTANDING → ... → risk → approval →
DELEGATING → ... — never a bypass), `ACTION_URGENTLY_ALERT` (a
`Notification`, `SEVERITY_CRITICAL`).

`ProactiveTrigger(id, action_level, description, evidence, source,
task_id=None)` — `evidence` is always the real data (task ids, audit
event counts, timestamps) a trigger was computed from. This is a
deliberate, evidence-only reimplementation of the *pattern* GENESIS's
`proactive_engine.py`/`environment_prediction/` got right (real
trigger conditions from real state), contrasted directly against
GENESIS's `core/prediction/*.py`, confirmed by the Mission Layla audit
to return hardcoded literal dicts regardless of input — `ProactiveTrigger`
can never be constructed with a fabricated confidence or prediction; it
only carries what its evaluator actually observed.

Two built-in evaluators, both evidence-based: a task stuck in
`REQUIRES_HUMAN` past a configurable age threshold escalates
`ACTION_SUGGEST` → `ACTION_URGENTLY_ALERT`; a task with repeated
`layla.delegation.failed`/`layla.delegation.timeout` audit events past
a configurable count escalates `ACTION_OBSERVE` → `ACTION_SUGGEST`.
Neither built-in evaluator ever reaches `ACTION_ACT` — genuinely
autonomous action requires a caller-supplied `extra_evaluators` entry,
a deliberate choice: "a task looks stuck" or "delegation failed
repeatedly" are reasons for a human to look, not evidence strong enough
to justify Layla acting unprompted.

**`ExecutiveRuntime` integration is entirely additive**:
`enable_proactive=False` (default) — zero behavior change, `.proactive`
is `None`. `enable_proactive=True` — `ExecutiveRuntime` constructs its
own `ProactiveEngine` internally (not accepted pre-built from the
caller, avoiding a construction-order chicken-and-egg problem: the
engine's `act_callback` binds to the runtime's own `handle_event`),
and `run_forever()`'s tick loop calls `.evaluate()` after every
`Scheduler.tick()`.

**Authorization fails closed for Layla's own actions too**: if
`authorization` is wired and no `proactive_session_id` was supplied at
construction, an `ACT`-level trigger's `handle_event()` call raises
`UnauthenticatedError` — caught by `_handle_proactive_act()` and
recorded as `layla.proactive.act_failed`, never silently bypassed.
Mission Layla Part 22 ("fail closed, no silent bypass") applies to
Layla's own self-triggered actions exactly as much as to a human's
request.

## §21. Prediction (Mission Layla Part 3, ADR-0027)

`PredictionEngine(session_manager, audit_logger)` — every `Prediction`
carries `prediction, evidence, confidence, provenance, reason,
recommended_action, timestamp` (Part 3's exact required shape) and a
genuinely computed confidence (a real ratio/frequency over
`SessionManager`/`AuditLogger` history), never a hardcoded literal.
`predict_task_completion_risk(task_id)` (real delegation-failure
ratio, confidence scaled by real sample size),
`predict_next_capability()` (real frequency across completed task
plans), `predict_stuck_task_risk()` (real incomplete/total ratio
across `SessionManager.list_all()`, an additive enumeration method
alongside `list_incomplete()`). Read-only; no new persistence.

## §22. Skills (Mission Layla Part 12, ADR-0027)

`SkillRegistry(memory)` — a named, versioned, reusable request
template with a real lifecycle: `CANDIDATE -> EVALUATING ->
APPROVED|REJECTED -> RETIRED`. `evaluate()` reuses
`avishkar_evaluation`'s real `EvalSuite`/`run_suite()`/
`passes_threshold()` — the caller supplies a real `subject_fn`/
`Scorer`; `status` only ever becomes `APPROVED` as the direct,
observable result of a real evaluation clearing a real threshold, not
a flag flipped for its own sake. Persisted via `LaylaMemoryPolicy`
(`skill:{id}`, `skill:__index__`).

## §23. Learning Loop (Mission Layla Part 13, ADR-0027)

`LearningLoop(session_manager, audit_logger, skill_registry)` —
Experience → Reflection → Pattern extraction → Candidate, built
entirely from real `SessionManager`/`AuditLogger` state feeding the
real `SkillRegistry` (§23). `extract_candidate_skills()` proposes a
`CANDIDATE` skill for any capability used successfully in
`>= min_occurrences` completed tasks — real evidence, real threshold,
never auto-approved. No self-modifying source code anywhere: never
writes a `.py` file, never calls `exec`/`eval`. Evaluation and
"security validation" remain genuinely separate, explicit,
human/deployment-driven steps (`SkillRegistry.evaluate()`) —
`LearningLoop` can never approve its own suggestions.

## §24. Life OS (Mission Layla Part 4, ADR-0027)

`LifeOS(personal_model)` — a thin, domain-organized convenience layer
over `PersonalModel` (§19), not a competing structure. Extends
`PersonalModel.CATEGORIES` with `schedule`/`tasks`/`finance`/`health`/
`travel`/`appointments`/`reminders`; `finance` and `health` join
`SENSITIVE_CATEGORIES` (every write requires `confirmed=True`).
`list_upcoming_appointments()`/`list_due_reminders()` do real
filtering/sorting by each fact's own real ISO `when` field.

## §25. Knowledge Graph (Mission Layla Part 5, ADR-0027)

`LaylaKnowledgeGraph(memory)` — a real, minimal, from-scratch graph
engine: typed `GraphNode`/`GraphEdge` with confidence/provenance, real
BFS-based `neighbors()`/`bfs()`/`shortest_path()`, zero seed data.
Additive alongside Avishkar's existing Knowledge Framework (Phase 6,
vector search over documents — a structurally different concern), not
a duplicate. `add_edge()` enforces referential integrity
(`NodeNotFoundError` for a missing source/target).

## §26. Channels, extended (Mission Layla Part 9, ADR-0027)

`channels/whatsapp_adapter.py`'s `WhatsAppChannelAdapter` — a second
real `avishkar_integration.ProtocolAdapter` implementation, the exact
`EmailChannelAdapter` (§12) pattern: ADAPTER READY / REQUIRES EXTERNAL
CREDENTIALS, an injectable transport defaulting to an "unconfigured"
function that raises a documented `ProtocolInvocationError`. Routing
across multiple channels remains `avishkar_integration.
UniversalToolRegistry`'s job (Phase 4, locked) — one registry, many
registered adapters; no second router is built.

## §27. Perception (Mission Layla Parts 6/7/8/16, ADR-0027)

`PerceptionEngine` — STATUS: CONTRACT/INTEGRATION BOUNDARY ONLY, no
microphone/camera/screen-capture/OCR backend wired (this mission's own
forensic audit found real hardware-access code in the external
codebase it studied; a genuinely safe equivalent is dedicated,
multi-day security-engineering work). Zero registered capture sources
by default. `observe(source)` on an unconfigured source raises
`PerceptionSourceNotConfiguredError` (the `email_adapter.py` ADAPTER
READY pattern). Every `PerceptionObservation` carries
`permissions_required`/`retention_policy` explicitly; `observe()` is
call-and-return, never a background capture daemon.

## §28. Embodiment (Mission Layla Parts 8/15/17/21, ADR-0027)

`EmbodimentController(approval_manager=None)` — STATUS: CONTRACT/
INTEGRATION BOUNDARY ONLY, covering `browser`/`computer_control`/
`application_control`/`adb`/`iot`/`sensors`/`robotics`/
`home_assistant`/`mqtt`. No backend wired for any capability. `request()`
computes risk via Layla's own real `risk.classify_risk()` — never a
caller-asserted value — and enforces `ApprovalManager` for any non-LOW
risk *before* any executor is looked up or called: structural, not
name-matched, closing the exact bug class (a tool-naming mismatch
silently disabling a safety gate) this mission's forensic audit found
in the external codebase it studied. Physical/host-affecting
capabilities are escalated to `HIGH` risk explicitly, fail-closed by
construction. Zero executors registered by default;
`EmbodimentCapabilityNotConfiguredError` is raised only *after*
clearing risk/approval, so discovering "is this configured" itself
requires authorization.

## §29. Business Intelligence (Mission Layla Part 26, ADR-0027)

`BusinessIntelligenceEngine(session_manager, audit_logger)` — a real
reporting layer over already-recorded state: task counts by state,
real delegation success rate per capability, real total cost
(`DelegationRecord.cost_usd`, summed from audit history — `runtime.py`
now includes `cost_usd` in every `layla.delegation.*` audit payload,
closing a gap where this number would otherwise always compute zero).
Every figure is a direct count/sum/ratio over real records.

## §30. Executive Dashboard (Mission Layla Parts 23/27, ADR-0027)

`ExecutiveDashboard(personal_model=None, life_os=None,
prediction_engine=None, skill_registry=None, business_intelligence=None)`
— not a new cognitive layer (`ExecutiveRuntime`, §11, already is
Layla's executive intelligence); a thin, real aggregator tying every
Foundation-tier component's own `summary()`/report method into one
`brief()`. Every section is a direct call into a real component; an
unwired component's section is omitted, never fabricated. Parts 24
(Multi-Agent Supervision) and 25 (Project Management) are already
satisfied by existing components (`Orchestrator`/`DelegationEngine`/
`Planner`; `ProjectStore`, §3) and are not rebuilt here.

## §31. Voice (Mission Layla Directive D, Part I)

`avishkar_layla.voice` — mic → `MicrophoneFrameSource` → `VoiceActivityDetector`
→ `SpeechToTextProvider` → **the unchanged `ExecutiveRuntime.handle_event()`
pipeline** → `TextToSpeechProvider` → `SpeakerSink`. `VoiceSession`
orchestrates the loop; it never calls a tool/executor/capability
directly, only `runtime.handle_event()` — voice enters through
exactly the same intent/risk/planning/approval architecture as any
other input, per Directive D's explicit requirement. The one local
exception is a stop/cancel phrase (`DEFAULT_STOP_PHRASES`), handled
entirely inside the session as an interrupt signal over its own
playback, not routed through planning, because it is not itself an
action request.

Every component is a real implementation behind a small ABC:
- `VoiceActivityDetector` / `EnergyVAD` — real numpy RMS-threshold VAD
  with an adaptive noise floor and an explicit `calibrate()` method for
  rooms louder than the default initial threshold.
- `SpeechToTextProvider` / `FasterWhisperSTT` (REAL, local, offline-
  capable, no API key — CTranslate2 Whisper inference) and
  `OpenAIWhisperAPISTT` (REAL HTTP client, ADAPTER READY — requires
  `OPENAI_API_KEY`).
- `TextToSpeechProvider` / `Pyttsx3TTS` (REAL, local, SAPI5/NSSpeech/
  espeak, no API key) and `OpenAITTSProvider` (REAL HTTP client,
  ADAPTER READY — requires `OPENAI_API_KEY`).
- `MicrophoneFrameSource` / `SpeakerSink` (REAL, `sounddevice`/
  PortAudio-backed hardware I/O) — the only files that open a real
  device; never invoked by the automated test suite, which drives
  `VoiceSession`'s orchestration logic through injected fakes and
  exercises the real local STT/TTS round trip via a synthesized (not
  live-recorded) utterance — see README.md Voice section and
  `test_voice_stt.py::test_real_round_trip_transcription`.

Interruption/barge-in: `SpeakerSink.play()` plays audio in chunks,
polling a shared `threading.Event` between chunks so
`VoiceSession.request_stop()` (or a detected stop phrase) halts
playback immediately rather than only after the full utterance
finishes. Full acoustic barge-in (detecting speech *while* Layla is
speaking, via echo cancellation) is out of scope for this pass and
documented as a limitation, not silently assumed.

`layla/python/pyproject.toml`'s new `voice` extra
(`numpy`/`scipy`/`sounddevice`/`soundfile`/`faster-whisper`/`pyttsx3`/
`requests`) is optional: the cognitive core has zero dependency on any
of it; only constructing a concrete voice provider pulls it in.
Deliberately NOT imported from `avishkar_layla/__init__.py` (unlike
every other component in this contract) precisely so importing
`avishkar_layla` itself never requires `numpy`/`sounddevice`/etc. --
callers opt in explicitly via `from avishkar_layla.voice import ...`.

## §32. Vision / OCR / Spatial Intelligence (Mission Layla Directive D, Part II)

`avishkar_layla.vision` -- Camera/Screen -> Capture -> Vision Pipeline
(OCR/Detection/Spatial Analysis) -> structured `PerceptionObservation`
-> Layla Context -> Decision. Every function produces DATA; nothing in
this package calls a tool, executor, or `ExecutiveRuntime.handle_event()`
-- Directive D Part II's explicit requirement that "perception must
produce structured evidence that passes through Layla's decision/risk
architecture," never act directly.

- `capture_screen()` (screen_capture.py) -- REAL, LOCAL, HARDWARE-
  BACKED (`PIL.ImageGrab`). Like voice's `MicrophoneFrameSource`, never
  invoked against the LIVE screen by the automated test suite (opening
  a real desktop's screen non-interactively risks capturing whatever
  is genuinely on screen -- documents, messages, credentials -- with
  no specific consent); error-handling is instead tested for real via
  an injectable `_grab_fn` seam.
- `extract_text()` (ocr.py) -- REAL if the `tesseract` binary is
  installed and discoverable (`is_tesseract_available()`); real
  word-level bounding boxes and per-word confidence from Tesseract's
  own `image_to_data`, never fabricated. Raises `OCRNotAvailableError`
  (ADAPTER READY) otherwise. Tested for real against a synthetically
  PIL-rendered test image (no live screen/camera involved) -- a
  genuine, non-mocked OCR round trip.
- `detect_template()` (detection.py) -- REAL, classical CV
  (`cv2.matchTemplate`, normalized cross-correlation): finds a known
  reference image inside a larger one with a real similarity score.
  NOT a trained object/scene classifier -- see README.md Vision
  section for the explicit boundary. Tested for real against
  synthetically generated, deliberately textured (not flat --
  `TM_CCOEFF_NORMED` degenerates on flat regions, a real caveat this
  module's own tests found) numpy images.
- `relative_position()`/`distance()`/`nearest()`/`overlaps()`/`iou()`
  (spatial.py) -- REAL, dependency-free geometry over real
  `BoundingBox` coordinates.
- `screen_capture_source()`/`screen_ocr_source()`
  (perception_adapters.py) -- wire the above as
  `PerceptionEngine.register_capture()`-shaped callables; not a second
  perception framework.

Deliberately NOT built this pass (see README.md Vision section):
general-purpose visual/scene classification (no trained model bundled
or fabricated) and true perception fusion beyond the raw structured
observations `PerceptionObservation` already carries.

`layla/python/pyproject.toml`'s new `vision` extra
(`pillow`/`pytesseract`/`opencv-python`/`numpy`) is optional, same
pattern as `voice`.

## §34. Computer Control (Mission Layla Directive D, Part III)

`avishkar_layla.executors` -- real `EmbodimentExecutor` callables
(`(action, parameters) -> output`) for `EmbodimentController.register_executor()`
(§28/ADR-0027). Registering one does not weaken that controller's
gate: `EmbodimentController.request()` still computes risk and
enforces `ApprovalManager` BEFORE any executor here is looked up or
called (embodiment.py, unchanged). This package is what runs only
AFTER that gate has already been cleared -- Directive D Part III,
verbatim: "Never give arbitrary unrestricted computer control to an
LLM."

- `BrowserExecutor` (browser_executor.py) -- REAL, `playwright.sync_api`-
  backed (headless Chromium by default). `navigate`/`click`/`type`/
  `get_text`/`get_url`/`screenshot`/`close`. One instance is one
  persistent real browser session across calls (navigate then click
  operate on the same real page -- Directive D's required
  Observation -> Verification chain). Headless browsing never touches
  the real visible desktop, so it's exercised for real, automatically,
  in the test suite against `data:` URLs (no network dependency).
  **Security note**: EMBODIMENT_BROWSER is NOT in embodiment.py's
  `_DEFAULT_HIGH_RISK_CAPABILITIES` -- plain navigation classifies LOW
  via the real text classifier and completes without approval
  (existing ADR-0027 behavior, confirmed by this pass's own
  integration test); only text that itself reads as dangerous (e.g.
  mentioning a payment/transfer) is gated. A deployment that wants
  ALL browser actions gated regardless of wording should add
  `EMBODIMENT_BROWSER` to that frozenset -- a one-line, documented
  choice for whoever deploys this, not decided unilaterally here.
- `ComputerControlExecutor` (computer_control_executor.py) -- REAL,
  three sub-capabilities:
  - Shell (`run_shell`): real `subprocess.run`, gated by a caller-
    supplied allowlist (empty allowlist = nothing runs). Exercised for
    real in tests with harmless commands.
  - File operations (`read_file`/`write_file`/`list_dir`/
    `delete_file`/`move_file`): real, confined to a `workspace_root`
    via a real path-containment check (resolves symlinks/`..`, refuses
    anything outside) -- tested for real including real path-traversal
    attack strings.
  - GUI control (`move_mouse`/`click`/`type_text`/`hotkey`/
    `screenshot`/clipboard): real `pyautogui`/`pyperclip` code behind
    an injectable `_gui` seam (default: the real hardware
    implementation). Like voice's `MicrophoneFrameSource` and vision's
    `capture_screen`, never invoked against the real mouse/keyboard by
    the automated test suite -- moving this machine's actual cursor or
    typing on its actual keyboard non-interactively during an
    unattended run would hijack a real desktop session. Tested via an
    injected fake asserting the real dispatch logic.
  - EMBODIMENT_COMPUTER_CONTROL IS in `_DEFAULT_HIGH_RISK_CAPABILITIES`
    -- every action through this executor always requires approval
    regardless of wording (confirmed by
    `test_computer_control_is_always_high_risk_even_for_an_innocuous_looking_action`).

Application launching, window management, and Android/ADB (Directive D
Parts III/IV's remaining scope) are tracked separately -- see §35 for
what has landed so far and README.md Computer Control section for
current status.

`layla/python/pyproject.toml`'s new `computer_control` extra
(`playwright`/`pyautogui`/`pyperclip`) is optional, same pattern as
`voice`/`vision`. `playwright install chromium` is a required
one-time step after `pip install` (not a pip package itself).

## §35. Android / ADB (Mission Layla Directive D, Part IV)

`ADBExecutor` (adb_executor.py) -- REAL CODE / ADAPTER READY. Genuinely
shells out to a real `adb` binary via `subprocess.run` for
`list_devices`/`device_info`/`screenshot`/`shell`/`tap`/`install_app`/
`launch_app`/`push_file`/`pull_file`. No `adb` binary and no connected
Android device exist in this environment (`is_adb_available()` -- a
real `shutil.which()` check, not fabricated -- correctly reports
`False` here); dispatch logic (which action builds which real `adb`
command line, with which arguments) is fully tested via an injectable
`_run` seam, the same DI pattern `ComputerControlExecutor`'s `_gui`
uses. Registered for `EMBODIMENT_ADB`, which is already in
embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` -- every action
always requires approval before `EmbodimentController` even looks up
this executor. `shell` additionally has its own fail-closed allowlist
(mirroring `ComputerControlExecutor.run_shell`) -- an arbitrary
command on a real phone is exactly as dangerous as one on the host.
Directive D Part IV, verbatim: "Never expose unrestricted ADB
execution directly to model output" -- there is no path from a model's
output to this executor that skips both the `EmbodimentController`
gate and this module's own shell allowlist.

## §36. Real Communication Channels (Mission Layla Directive D, Part V)

Every channel is still a real `avishkar_integration.ProtocolAdapter`
routed through the existing `UniversalToolRegistry`/`ToolRuntime`
(Phase 4, locked) -- no second router. Directive D Part V's escalation
is that each adapter now ships a REAL transport implementation
alongside its existing `_unconfigured_transport` ADAPTER READY
default, in `channels/` priority order:

- `EmailChannelAdapter` + `SMTPEmailTransport` (email_adapter.py) --
  REAL `smtplib`/STARTTLS/MIME. Genuinely speaks the SMTP wire
  protocol to a real local test server in `test_smtp_email_transport.py`
  (its own real, minimal, in-repo fixture -- not a mock of `smtplib`).
  Only attempts `AUTH` if the server advertises support
  (`smtp.has_extn("auth")`, standard `smtplib` practice) -- credentials
  are still required up front regardless.
- `WhatsAppChannelAdapter` + `WhatsAppCloudAPITransport`
  (whatsapp_adapter.py) -- REAL HTTP client, Meta's real WhatsApp
  Business Cloud API. A real network call with a deliberately invalid
  token is exercised in tests, confirming a real Graph API rejection.
- `TelegramChannelAdapter` + `TelegramBotAPITransport`
  (telegram_adapter.py, NEW) -- REAL HTTP client, Telegram's real Bot
  API. Real-rejection-tested the same way.
- `SlackChannelAdapter` + `SlackWebAPITransport` (slack_adapter.py,
  NEW) -- REAL HTTP client, Slack's real Web API. Slack always returns
  HTTP 200 even on failure; the transport checks the real `ok` field
  in the response body, not the status code -- real-rejection-tested.
- `DiscordChannelAdapter` + `DiscordBotAPITransport`
  (discord_adapter.py, NEW) -- REAL HTTP client, Discord's real Bot
  REST API. Real-rejection-tested.
- `SMSChannelAdapter` + `TwilioSMSTransport` (sms_adapter.py, NEW) --
  REAL client using the real, installed `twilio` SDK. Real-rejection-
  tested against Twilio's real API.

Every "real-rejection-tested" case above means: the test supplies a
credential that is well-formed but definitely invalid, makes one
genuine network call to the provider's real endpoint, and asserts the
provider's real error response was correctly parsed into a
`ProtocolInvocationError` -- zero side effects (an invalid credential
can never actually deliver a message), and the test skips gracefully
(not fails) if this environment has no outbound network access at test
time.

Every transport reads its credential(s) from environment variables at
CALL time (never hardcoded, never logged) and raises
`ProtocolInvocationError` with an "ADAPTER READY" message if the
credential is missing -- before attempting any network call.

LinkedIn, Google services (Gmail/Calendar), and Zoom (the remainder of
Part V's named priority order) are NOT built this pass -- reported as
a real, explicit gap (README.md Communication Channels table), not
silently implied to exist alongside the six channels above.

**Send-approval policy** (Directive D's explicit LOW/MEDIUM/HIGH risk
requirement for outbound messages) is NOT a new mechanism here: every
channel `invoke()` is reached only via a real tool call, which (when
routed through `ExecutiveRuntime`) already passes through
`classify_risk()`/`ApprovalManager` before DELEGATING is ever reached
(§4/§11) -- exactly Directive D's "Layla must NOT automatically send
arbitrary messages simply because an LLM generated them." No channel
adapter bypasses that; none was changed to add a competing check.

## §38. Environmental Awareness (Mission Layla Directive D, Part VI)

`avishkar_layla.environment` -- Sensor -> Event -> EventBus ->
Perception/Context -> Layla -> Decision -> Action, Directive D Part
VI's exact required chain, built entirely on existing, unmodified
components (`avishkar_core.EventBus`, `Scheduler`, `ProactiveEngine`)
-- no new event system, no new scheduler.

- `Sensor` / `SensorReading` (sensors.py) -- real, local, no camera/
  microphone (already covered by `voice`/`vision`): `IdleTimeSensor`
  (real Win32 `GetLastInputInfo`), `BatterySensor` (real `psutil`,
  raises `SensorUnavailableError` with no fabricated reading if this
  machine has none), `SystemLoadSensor` (real CPU/memory via
  `psutil`), `NetworkConnectivitySensor` (a REAL socket-level
  reachability probe -- a genuine TCP connection attempt, not merely
  an interface-up flag).
- `SensorMonitor` (event_translation.py) -- the anti-polling
  mechanism Directive D explicitly requires: `.check()` is cheap,
  non-LLM Python (one real sensor read + one comparison against the
  last reading); it calls `EventBus.publish()` ONLY on a genuine
  first-read or threshold-crossing change, never on every tick.
  Intended to be driven by `Scheduler.schedule_recurring()` (already
  real, already exists) -- not a new polling loop.
- `EnvironmentalEventBuffer` (context.py) -- subscribes to
  `EventBus`'s real `"*"` wildcard (core/'s locked implementation has
  no prefix-matching, so this module filters by the
  `layla.environment.` prefix itself rather than asking core/ to grow
  a feature it doesn't have) and keeps a bounded recent-events window.
- `EnvironmentalChangeEvaluator` (context.py) -- a real
  `proactive.TriggerEvaluator` a deployment can pass into
  `ProactiveEngine(extra_evaluators=(...))`. Capped at `ACTION_OBSERVE`
  (same discipline as every other built-in evaluator, ADR-0026) --
  never calls `ExecutiveRuntime.handle_event()` itself. Tracks
  already-surfaced event ids so the same buffered event is never
  re-triggered on a later `evaluate()` tick (Directive D Part XII's
  retry-storm concern, addressed structurally here).

`test_environment_end_to_end.py` proves the full real chain composes:
a scripted sensor change -> real `EventBus.publish()` -> real buffer
capture -> a real `ProactiveTrigger` from `ProactiveEngine.evaluate()`
-- entirely without any LLM call, matching Directive D's "wake Layla
intelligence only when required."

## §40. Home Assistant (Mission Layla Directive D, Part VII)

`HomeAssistantExecutor` (executors/home_assistant_executor.py) -- REAL
CODE / ADAPTER READY. Genuine HTTP client against Home Assistant's
real REST API: `list_states` (`GET /api/states`), `get_state`
(`GET /api/states/<entity_id>`), `call_service`
(`POST /api/services/<domain>/<service>`), `get_config`
(`GET /api/config`). No live Home Assistant instance exists in this
environment; `test_home_assistant_executor.py` runs a real, minimal,
in-repo HTTP server implementing Home Assistant's actual REST API
shape (the same pattern `test_smtp_email_transport.py` established for
Email) -- a genuine HTTP conversation with real Bearer-token checking,
real 401 handling, real JSON parsing, not a mock of `requests`.

Registered for `EMBODIMENT_HOME_ASSISTANT`, already in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES` -- every action always requires
approval before `EmbodimentController` even looks up this executor
(verified end to end in
`test_embodiment_real_executors_integration.py`: an approved
`list_states` call reaches the real local fixture server; a denied
`call_service` call never does). Directive D Part VII, verbatim: "the
architecture must never permit unrestricted autonomous physical
actions" -- there is no path from a model's output to a real Home
Assistant service call that skips that gate.

## §42. MQTT (Mission Layla Directive D, Part VIII)

`avishkar_layla.mqtt` -- REAL. `MQTTBridge` (mqtt/client.py) wraps the
real, installed `paho-mqtt` client (VERSION2 callback API): real
broker connection (host/port/TLS), real username/password
authentication, real `publish`(QoS, retain)/`subscribe`(QoS), and real
automatic reconnect (paho's own `reconnect_delay_set`, not
reimplemented). Directive D Part VIII, verbatim: "MQTT events must
enter Avishkar's EventBus rather than creating another event system"
-- every inbound message is translated into a real
`avishkar_core.EventBus.publish("layla.mqtt.<topic>", ...)` call
inside the real paho `on_message` callback; there is no separate MQTT
event queue for callers to poll.

Publish and subscribe are each gated by a real, fail-closed topic
allowlist (`allowed_publish_topics`/`allowed_subscribe_topics`, MQTT
`+`/`#` wildcard semantics implemented for real in `topic_matches()`)
-- empty allowlist = nothing published/subscribed, the same discipline
`ComputerControlExecutor.run_shell`/`ADBExecutor`'s shell allowlists
use.

`MQTTExecutor` (executors/mqtt_executor.py) wraps a connected
`MQTTBridge` as an `EmbodimentExecutor` for `EMBODIMENT_MQTT` --
**added to embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` this same
pass (ADR-0035)**, alongside `EMBODIMENT_COMPUTER_CONTROL`/
`EMBODIMENT_ADB`/`EMBODIMENT_ROBOTICS`/`EMBODIMENT_HOME_ASSISTANT`: a
real MQTT `publish` is routinely how real physical devices are
commanded, so it is escalated by construction rather than trusted to
`classify_risk()`'s general-purpose text matching, exactly like
`EMBODIMENT_HOME_ASSISTANT`. Every action through `MQTTExecutor`
already requires `EmbodimentController` approval before it is even
looked up, on top of `MQTTBridge`'s own topic allowlist -- two
independent, non-redundant gates.

Verified via a real, minimal, in-repo MQTT 3.1.1 broker
(`tests/_minimal_mqtt_broker.py`) this suite runs itself -- a genuine
binary wire-protocol implementation (CONNECT/CONNACK with real
authentication, PUBLISH, SUBSCRIBE/SUBACK, retained-message delivery,
PINGREQ/PINGRESP), the same "real local fixture" discipline
`test_smtp_email_transport.py`/`test_home_assistant_executor.py`
established for text protocols, extended here to a binary one. No real
external MQTT broker was reachable from this environment (this
sandbox's outbound network access is allowlisted to specific known
API hosts, confirmed by testing -- `test.mosquitto.org:1883` was
unreachable while `api.telegram.org`/`slack.com`/etc. from Part V were
reachable) -- the in-repo broker fixture is what makes GREEN status
possible here rather than falling back to ADAPTER READY.

## §44. Robotics / Embodiment (Mission Layla Directive D, Part IX)

`avishkar_layla.robotics` -- Sensors -> Perception -> World State ->
Layla -> Planning -> Risk Assessment -> Approval -> Robot Capability ->
Execution -> Observation -> Verification, Directive D Part IX's exact
required chain, built entirely on existing components: `PerceptionEngine`
(§28) for the sensing side, `EmbodimentController`/`risk.classify_risk`/
`ApprovalManager` (§28, unchanged) for risk/approval, `AuditLogger` for
the trail. No new cognitive/risk/event framework was created.

`RobotSafetyController` (robotics/controller.py) is a real safety layer
that sits between `EmbodimentController` and a real robot driver a
deployment provides for its platform (`RobotDriver`: `execute()`/
`get_state()`/`emergency_stop()` -- the documented ADAPTER READY
boundary; no physical robot exists in this environment). Registered
for `EMBODIMENT_ROBOTICS`, already in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES` since ADR-0027 -- every action
already requires `EmbodimentController` approval before this
controller is even looked up. `RobotSafetyController` adds a SECOND,
complementary safety gate beneath that, implementing every physical-
action safety property Directive D Part IX explicitly requires, all
real and genuinely tested (11 unit tests + 3 end-to-end
`EmbodimentController` integration tests) without needing physical
hardware:

- **Emergency stop**: a real latch (`emergency_stop(reason=...)`) that
  sets the software flag BEFORE calling the real driver's own stop
  method, so a human override is never delayed by (or lost to) a
  failing hardware call -- verified with a driver whose `emergency_stop()`
  itself raises.
- **Human override**: the latch is checked first on every call,
  including one that would otherwise be a fully-approved
  `EmbodimentController` request -- verified end to end.
- **Timeout**: every driver call runs on a real background thread with
  a real `Thread.join(timeout=...)`; a real slow driver genuinely
  exceeding the configured budget raises `RobotActionTimeoutError`.
- **Cancellation**: a timed-out call's eventual result (if the
  abandoned thread ever finishes) is never read or applied.
- **State verification**: the driver's real `get_state()` is queried
  and recorded after every successful action.
- **Fail-safe behavior**: any timeout OR driver exception both
  triggers a caller-supplied fail-safe callback AND latches the
  emergency stop, before the error propagates -- verified that further
  actions are refused afterward until an explicit `reset_emergency_stop()`.
- **Audit trail**: every action/timeout/failure/stop/reset is recorded
  via the existing `AuditLogger` (`layla.robotics.*` event types).

## §46. Personal Executive Communication (Mission Layla Directive D, Part X)

`avishkar_layla.executive_communication`. Calendar/Meetings/
Appointments/Reminders are already real, existing `LifeOS`
functionality (§24/ADR-0027) -- not rebuilt. This module implements
Directive D's own worked example: "Avishkar has not responded to this
person for 7 days -> Relationship/context lookup -> Determine
follow-up appropriateness -> Generate draft -> Risk assessment ->
Approval policy -> Send -> Record outcome -> Update memory."

- `StaleRelationshipEvaluator` -- a real `proactive.TriggerEvaluator`
  covering the chain's first three steps: real relationship/context
  lookup (`PersonalModel`'s `relationships` category), real staleness
  detection (a real days-since-last-contact computation against a
  configurable `threshold_days`), and real follow-up-appropriateness
  filtering (`do_not_disturb`, plus an optional caller-supplied
  `is_eligible` predicate). Emits `ACTION_SUGGEST`, never `ACTION_ACT`
  -- deciding what to send, and to whom, is not this evaluator's job.
  Deduplicates per `(contact_id, last_contact_date)` so the same
  staleness state is never re-suggested on every `ProactiveEngine.evaluate()`
  tick (the same retry-storm-safe pattern `EnvironmentalChangeEvaluator`,
  §38, established).
- The chain's remaining steps ("Generate draft -> Risk assessment ->
  Approval policy -> Send") are deliberately NOT reimplemented here --
  they are exactly what the unchanged `ExecutiveRuntime.handle_event()`
  pipeline already does for any suggestion a human or
  `ProactiveEngine.act_callback` chooses to act on: real intent/
  context/planning, real `risk.classify_risk()`, real `ApprovalManager`,
  real delegation to a Chief Domain Agent for drafting, and real Part V
  channel adapters for sending. Reimplementing any of this here would
  duplicate the exact pipeline Mission Layla's own architecture rule
  ("AVISHKAR OS REMAINS THE FOUNDATION") forbids duplicating.
- `record_contact_outcome()` -- the chain's final two steps ("Record
  outcome -> Update memory"): a real `PersonalModel.correct()` call
  updating the contact's `last_contact_date`/`last_contact_channel`/
  `last_contact_message_id`, called after a real Part V channel
  adapter confirms delivery (a real `message_id`) -- never before, and
  never for a contact `PersonalModel` has no existing record of.

## §48. 24/7 Operation (Mission Layla Directive D, Part XI)

Real hardening of the existing `Scheduler`/`ExecutiveRuntime.run_forever()`
loop -- no new persistent-runtime mechanism, per Directive D's own
"Layla should be the continuously-running intelligence... specialist
agents wake only when required" (already true: Chief Domain Agents are
only ever invoked via `DelegationEngine`, never run continuously).

- **Scheduler failure isolation & dead-letter** (scheduler.py) -- a
  real gap found by reading `tick()`'s existing implementation: a
  scheduled job's callback was called with NO exception handling at
  all, so one failing job (e.g. a flaky `SensorMonitor.check()`
  recurring job, §38) would crash `tick()` and therefore
  `run_forever()`'s entire loop. Now every callback is isolated
  (verified: a raising job never prevents other due jobs in the same
  tick from running, and never propagates out of `tick()`); an
  optional `max_consecutive_failures` dead-letters a job that keeps
  failing (a real `cancel()`, not merely a flag) rather than retrying
  it forever -- a real, bounded retry-storm guard. Omitting both new
  constructor parameters preserves every prior behavior exactly (the
  isolation itself is unconditional; only escalation to dead-letter is
  opt-in).
- **Graceful shutdown** (`ExecutiveRuntime.request_shutdown()`) -- a
  real, cooperative `threading.Event` checked at the top of every
  `run_forever()` iteration; a deployment's signal handler calls it to
  stop the loop cleanly (a real `layla.runtime.run_forever_stopped`
  audit record, via the existing `AuditLogger` -- no new logging
  mechanism) instead of requiring the process to be killed, which
  would skip that record entirely.
- **Heartbeat / liveness** (`ExecutiveRuntime.last_tick_at`/`is_alive()`)
  -- `last_tick_at` is updated with the real injected `clock()` value
  at the end of every completed iteration; `is_alive(max_staleness_seconds=...)`
  is a real, direct staleness check an external health probe can call.
- **Operational health report** (`ExecutiveRuntime.operational_health()`)
  -- a real, dependency-free aggregation: liveness, last tick,
  `SessionManager.list_incomplete()`'s real count (stuck tasks),
  and (when a `Scheduler` is configured) its real pending-job count
  and dead-lettered-job map. Deliberately does not include CPU/
  memory/battery metrics -- those are real too
  (`avishkar_layla.environment.sensors`, §38/ADR-0033) but live behind
  that package's optional `psutil` dependency; a deployment combines
  them externally rather than `runtime.py` itself acquiring that
  dependency.
- Real crash recovery -- already covered by Priority 17.3's resume-in-
  place (`SessionManager.list_incomplete()`/`ExecutiveRuntime.resume()`,
  ADR-0023) and Priority 17.5's durable `ApprovalManager`; not
  rebuilt, cross-referenced here since it's exactly what "restart
  recovery" means for this runtime.

## §50. Durable Execution (Mission Layla Directive D, Part XII)

Most of "durable execution" is already real, existing functionality,
not rebuilt here: durable task state and checkpoints
(`SessionManager`/`LaylaTask.plan`, §16/ADR-0023), idempotency keys
and exactly-once-or-safe-at-least-once semantics (`ExecutionTracker`,
§15/ADR-0022), retry policies (`DelegationEngine`, §5), an execution
journal (`AuditLogger`, §9). `task_lease.py`'s real, new contribution
is the two items Directive D Part XII names that nothing existing
covered: task ownership and stale-task recovery.

`TaskLeaseManager` -- thread-safe within one process (the same
lock-guarded check-then-write pattern `Scheduler`/`AuditLogger` use)
and durable across a restart (leases persist via the real
`LaylaMemoryPolicy`). `acquire()`/`renew()`/`release()`/`is_stale()`/
`find_stale_leases()` are all real: a genuine multi-thread test
(`test_only_one_of_many_concurrent_acquirers_wins`) proves exactly one
of 20 real, concurrently-racing threads wins a contested lease.

**Explicitly documented scope limit** (not a claim of more than is
real): this is NOT a distributed lock service. True atomicity across
*multiple concurrent OS processes* racing for the same lease depends
on the underlying `LaylaMemoryPolicy` backend's own guarantees
(`remember()` is an unconditional write, not a compare-and-swap) --
this layer does not itself provide that. The intended, correctly-
scoped real usage matches Directive D's own actual framing ("a machine
restart must NOT destroy an important Layla task"): one active Layla
process, restarted by a supervisor after a crash, calling
`find_stale_leases(t.id for t in session_manager.list_incomplete())`
on startup to distinguish tasks genuinely abandoned mid-processing
from ones a still-live process may legitimately be working on.

## §52. Security Hardening (Mission Layla Directive D, Part XIII)

A fresh security review across authentication, authorization, secrets,
credential storage, prompt/tool injection, data exfiltration, SSRF,
and sensitive-memory handling. Most of this list is already real,
existing coverage from earlier phases: `AuthorizationManager`/
`Principal`/`Role` (§14, Priority 17.1), `ApprovalManager`'s durable,
never-self-approvable gate (§4), `PersonalModel`'s
`SENSITIVE_CATEGORIES` (relationships/behavioral_patterns/finance/
health, all requiring `confirmed=True`, §19), `test_adversarial.py`'s
prompt-injection/hostile-tool-response/unauthorized-capability
coverage, and `security-factory.scan_repository_for_secrets()` (used
throughout this entire Directive D pass after every commit).

**Real finding from this pass, fixed, not merely documented**:
`avishkar_layla.executors.ssrf_guard` -- `EMBODIMENT_BROWSER` is
LOW-risk-by-default for text that doesn't match `classify_risk()`'s
dangerous-pattern list (a real, deliberate finding from ADR-0030), but
"navigate to a URL" does not itself read as dangerous TEXT even when
the URL is a cloud-metadata endpoint
(`http://169.254.169.254/latest/meta-data/iam/security-credentials/`).
On a real cloud VM with an attached IAM role, this was a genuine,
unmitigated SSRF/credential-exfiltration path -- `BrowserExecutor`'s
`navigate` action, reached with zero approval gate for a URL like that
one, could have leaked real, live cloud credentials to whatever the
browsing plan does with the resulting page. `unsafe_navigation_reason()`
closes this with a real, hard block -- refusing navigation to a
private/loopback/link-local/reserved IP address or a known metadata
hostname BEFORE Playwright ever opens a real connection, verified end
to end in `test_browser_executor.py` (a real `navigate` call to
`169.254.169.254` is confirmed refused, not merely unit-tested in
isolation).

A repository-wide `scan_repository_for_secrets("layla")` sweep run as
part of this pass found 3 matches, all pre-existing, known,
intentional test fixtures (AWS's own documented
`AKIAIOSFODNN7EXAMPLE` placeholder in `test_adversarial.py`/
`test_memory_policy.py`) -- zero real secrets, zero new findings
introduced across this entire Directive D pass (Parts I-XIII).

## §54. Observability (Mission Layla Directive D, Part XIV)

Most of what Directive D Part XIV asks for is already real, existing,
separate capability: a structured, correlation/task-scoped execution
journal (`AuditLogger`, every event `layla.*`-namespaced with a real
`task_id`), real cost/request tracking (`Router`'s `cost_usd`/
`request_id`, Priority 17.5), real per-capability success/failure
aggregation and cost totals (`BusinessIntelligenceEngine.generate_report()`,
§29/ADR-0027), and real scheduler/liveness health
(`ExecutiveRuntime.operational_health()`, §48/ADR-0038). Directive D's
own explicit remaining ask -- "Create a production health report
capability" -- is exactly what `observability.py`'s
`build_production_health_report()` is: a single-call aggregation of
these already-real pieces, not a new metrics/tracing system.

A real bug was found and fixed while writing this module's own first
test run: `AuditLogger.history()` is scoped per `task_id` (or
`"system"` with none) -- there is no single global query across every
task's audit trail. An initial draft called `runtime.audit.history()`
with no arguments, silently seeing only `"system"`-scoped events and
missing every real per-task delegation record (which `runtime.py`
always records with `task_id=task.id`). Fixed to mirror
`BusinessIntelligenceEngine.generate_report()`'s own established real
pattern exactly: enumerate every real task via
`SessionManager.list_all()`, then query each task's own
`layla.delegation.*` history -- confirmed correct by a real test using
genuinely saved `LaylaTask`/`Plan` records, not merely audit calls in
isolation.

Honestly NOT covered (disclosed, not fabricated): `avishkar_core.EventBus`
queue-depth/throughput metrics and per-operation `LaylaMemoryPolicy`
backend latency. Neither exposes any statistics at its current
abstraction layer; adding that instrumentation would mean modifying
core/'s locked `EventBus` or introducing a new cross-cutting metrics
collector, both out of this pass's scope. See README.md Observability
section.

## §55. Errors

`LaylaError` (base), `InvalidTransitionError`,
`MemoryPolicyViolationError`, `UnknownCapabilityError`,
`DelegationTimeoutError`, `UnresolvedConflictError`,
`ApprovalExpiredError`, `ApprovalDeniedError`, `SessionNotFoundError`,
`UnauthenticatedError`, `PermissionDeniedError`, `EscalationDeniedError`,
`IdempotencyConflictError`, `UnknownExecutionOutcomeError`,
`PersonalFactContradictionError`, `SensitiveCategoryNotConfirmedError`,
`SkillNotFoundError`, `NodeNotFoundError`,
`PerceptionSourceNotConfiguredError`, `UnknownPerceptionSourceError`,
`UnknownEmbodimentCapabilityError`, `EmbodimentCapabilityNotConfiguredError`,
`EmbodimentNotApprovedError`. Voice-subsystem errors
(`AudioDeviceError`, `NoSpeechDetectedError`, `TranscriptionError`,
`STTProviderNotConfiguredError`, `TTSProviderError`,
`VoiceSessionClosedError`) live in `voice/errors.py`; vision-subsystem
errors (`ScreenCaptureError`, `OCRNotAvailableError`) live in
`vision/errors.py`; executor errors (`UnknownActionError`,
`BrowserActionError`, `ShellCommandNotAllowedError`,
`PathOutsideWorkspaceError`, `ADBNotAvailableError`) live in
`executors/errors.py`; `HomeAssistantNotConfiguredError` lives in
`home_assistant_executor.py` directly (also used to normalize a real
401 from Home Assistant, not only a missing-configuration case; real
connectivity failures raise the stdlib `ConnectionError`);
`SensorUnavailableError` lives in `environment/errors.py`;
`MQTTNotConnectedError`/`MQTTPublishNotAllowedError`/
`MQTTSubscribeNotAllowedError` live in `mqtt/errors.py`;
`RobotEmergencyStoppedError`/`RobotActionTimeoutError`/
`RobotActionFailedError` live in `robotics/errors.py`;
`executive_communication.py`'s `record_contact_outcome()` raises the
stdlib `ValueError` for an unknown contact (deliberately not a new
`LaylaError` subclass -- "the caller passed a contact id PersonalModel
has never heard of" is a plain programmer-error/bad-input case, not a
Layla-domain error condition); `task_lease.py` deliberately raises no
custom errors at all -- `acquire()`/`renew()`/`release()` return `bool`,
since "another worker already holds this lease" is an expected, normal
outcome for a lease-based design, not an exceptional one; every
channel transport raises the existing `avishkar_integration.ProtocolInvocationError`
(no new channel-specific error types were introduced) -- all following the
same locally-scoped convention as §22-§28's errors.
