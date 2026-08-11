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

## §19. Errors

`LaylaError` (base), `InvalidTransitionError`,
`MemoryPolicyViolationError`, `UnknownCapabilityError`,
`DelegationTimeoutError`, `UnresolvedConflictError`,
`ApprovalExpiredError`, `ApprovalDeniedError`, `SessionNotFoundError`,
`UnauthenticatedError`, `PermissionDeniedError`, `EscalationDeniedError`,
`IdempotencyConflictError`, `UnknownExecutionOutcomeError`.
