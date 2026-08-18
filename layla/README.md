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
  |-- handle_event() / resume()   (Priority 17.3: two entry points, one
  |                                 shared, state-guarded _advance() pipeline)
  |-- StateMachine            (genuinely new: Layla's own explicit lifecycle)
  |-- IntentInterpreter        (genuinely new: real keyword classifier)
  |-- ContextBuilder            (composes) -> LaylaMemoryPolicy -> avishkar_agent.MemoryPolicy (Phase 5)
  |                                       -> avishkar_knowledge.KnowledgeBase (Phase 6)
  |-- Planner                    (genuinely new) -> CapabilityResolver (genuinely new)
  |-- ApprovalManager              (genuinely new risk tiering) -> avishkar_agent.ApprovalGate (Phase 3, reused)
  |-- DelegationEngine              (genuinely new typed wrapper) -> avishkar_agent.Orchestrator (Phase 3, reused)
  |     |                                                         -> avishkar_integration.RetryPolicy (Phase 4, reused)
  |     `-- ExecutionTracker (Priority 17.2, genuinely new)       -> LaylaMemoryPolicy (one storage mechanism, not a second)
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
├── python/avishkar_layla/       reference implementation (45 modules)
│   ├── channels/                   communication channel adapters (6 real transports, Directive D Part V, ADR-0032)
│   ├── environment/                 environmental awareness (Directive D Part VI, ADR-0033)
│   ├── voice/                      voice subsystem (Directive D Part I, ADR-0028)
│   ├── vision/                     vision/OCR/spatial subsystem (Directive D Part II, ADR-0029)
│   ├── mqtt/                        real MQTT bridge (Directive D Part VIII, ADR-0035)
│   ├── robotics/                    real robot safety layer (Directive D Part IX, ADR-0036)
│   ├── executive_communication.py   real stale-relationship follow-up chain (Directive D Part X, ADR-0037)
│   ├── task_lease.py                real task ownership/stale-task recovery (Directive D Part XII, ADR-0039)
│   ├── observability.py             real production health report (Directive D Part XIV, ADR-0041)
│   ├── deployment.py                real health server/graceful shutdown/backup-restore (Directive D Part XVII, ADR-0044)
│   └── executors/                  real EmbodimentController executors (Directive D Parts III-IV/VII-VIII, ADR-0030/0031/0034/0035)
├── deploy/
│   └── run_production.py           real, smoke-tested reference production entrypoint (Directive D Part XVII, ADR-0044)
├── Dockerfile                      base production runtime image (Directive D Part XVII, ADR-0044)
├── OPERATIONS.md                   operational runbook (Directive D Part XVII, ADR-0044)
├── examples/
│   ├── end_to_end_scenario.py       Part IX's real, narrated demonstration
│   ├── crash_recovery_scenario.py   resume-in-place demonstration (Priority 17.3)
│   └── personal_model_and_proactive_scenario.py  Mission Layla Parts 1/2/11
└── python/tests/                   583 tests (as of Directive D Part XVII; 1 live-gated, skipped by default)
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
`python layla/examples/crash_recovery_scenario.py` — a 5-step plan
"crashes" after 3 steps (simulated the same way every crash-recovery
test in this codebase does: a fresh runtime against the same on-disk
store); a second, brand-new runtime resumes the task and completes
only the 2 remaining steps, proving via a real orchestrator call count
that the 3 already-done steps are never re-run. See "Resume-in-Place /
Durable Execution," below.
`python layla/examples/personal_model_and_proactive_scenario.py` —
PersonalModel facts flow into a real task's context; a custom
ProactiveEngine trigger drives a real `handle_event()` call to
completion through `run_forever()`'s tick loop, not a bypass. See
"Personal Model" / "Proactive Intelligence," above.

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

# Idempotency & Side-Effect Safety (Priority 17.2, ADR-0022)

**Status: IMPLEMENTED** for the delegation path; **PARTIALLY
IMPLEMENTED** for direct tool invocation (see below).
`execution.classify_operation()` splits every action into `READ` /
`WRITE` / `HIGH_RISK` — a distinct axis from `risk.classify_risk`: risk
asks "how much harm"; this asks "does retrying this duplicate a
real-world effect." The default is fail-closed: unrecognized text
classifies as `WRITE`, never `READ`.

`ExecutionTracker` (`execution.py`) persists an `ExecutionRecord` per
idempotency key through the *same* `LaylaMemoryPolicy` every other
Layla component already uses (`kind="long_term"`,
`execution:{key}`) — one storage mechanism, not a second one. Lifecycle:
`REQUESTED -> AUTHORIZED -> APPROVED -> EXECUTING -> COMPLETED`, with
`REJECTED`/`CANCELLED`/`FAILED`/`EXPIRED` also terminal and `UNKNOWN`
deliberately **not** terminal — an uncertain outcome (e.g. a timeout on
a WRITE after the provider may already have accepted it) requires an
explicit `resolve_unknown()` call before anything retries it.

`DelegationEngine(..., execution_tracker=None)` — the same additive
pattern as `approval_manager=`/`authorization=`: omitted, behavior is
identical to Phase 16/17.1 (every original `test_delegation.py` test
still passes unmodified); supplied, every `delegate()` call is keyed
`{task_id}:{plan_step.id}` and:
- a `COMPLETED` record short-circuits — the real `Orchestrator` is
  **never invoked a second time** for that key;
- a record still `AUTHORIZED`/`APPROVED`/`EXECUTING`/`UNKNOWN` (claimed
  by a prior attempt — concurrent duplicate *or* a crash mid-flight,
  which look identical from here) **refuses** any non-`READ` retry,
  fail-closed;
- a timeout on a non-`READ` step lands on `UNKNOWN`, not `FAILED` —
  `FAILED` would imply "safe to retry," which a timeout does not
  guarantee.

`ExecutiveRuntime(..., execution_tracker=None)` threads the same
optional tracker into its `DelegationEngine` and exposes it via
`.executions` for a caller (or a recovery script, Priority 17.3) to
inspect or `resolve_unknown()` after `handle_event()` returns. See
`test_delegation_idempotency.py` (duplicate-call short-circuit,
timeout-to-UNKNOWN, `resolve_unknown()`-unblocks-retry, and a real
cross-instance crash-recovery proof using `FileMemoryPolicy` — a fresh
`ExecutionTracker` in a brand-new process against the same on-disk
store correctly refuses to blindly re-run a WRITE left `EXECUTING` by a
simulated crash) and `test_runtime_idempotency.py`.

**What's NOT built**: idempotency awareness inside `mcp-factory`'s
`UniversalToolRegistry`/`ToolRuntime`/`ProtocolAdapter` themselves —
those are Phase 4, locked, and this repository's own discipline is
"later frameworks wrap, never modify earlier locked frameworks." Layla
only ever reaches an external system *through* a delegated
`ChiefDomainAgent`'s own tool calls, so `ExecutionTracker` guards the
one seam Layla actually owns (`DelegationEngine.delegate()`); a
delegated agent's own direct `ToolRuntime.invoke()` calls are outside
this tracker's visibility today — real future work would thread an
idempotency key down through `ToolContract`/`ProtocolAdapter` itself,
which is a `mcp-factory` change, not a Layla one. No automatic
resolution of `UNKNOWN` outcomes (e.g. polling a provider's status API)
— `resolve_unknown()` is deliberately a manual, explicit call.

# Resume-in-Place / Durable Execution (Priority 17.3, ADR-0023)

**Status: IMPLEMENTED.** `ExecutiveRuntime.resume(task_id,
session_id=None) -> LaylaTask` reloads a persisted task and continues
it from exactly the state it was last checkpointed in — no
re-planning, no re-deciding an already-decided approval, and (when
`execution_tracker` is wired, Priority 17.2) no re-running an
already-completed delegation. This directly answers the directive's
own example: a 50-company research task that crashes after company 17
resumes from company 18, not from scratch — see
`layla/examples/crash_recovery_scenario.py` for a runnable, smaller-
scale (5 companies, crash after 3) proof.

`handle_event()` and `resume()` are two thin entry points around one
shared, re-entrant pipeline (`_advance()`): every stage is guarded by
the task's *current* `state`. A fresh task runs straight through,
identically to Phase 16/17.1; a reloaded task skips directly to its
first not-yet-done stage. This is deliberately **not** a second
workflow engine — it reuses the exact same `StateMachine`, `Planner`,
`ApprovalManager`, and `DelegationEngine` every other code path already
goes through (the Phase 17 directive's explicit instruction for this
priority).

Two new persisted `LaylaTask` fields make this possible: `plan` (the
actual `Plan`, not just `plan_id` — reconstructing a plan via the
`Planner` again on resume would be a *different* operation, not a
continuation) and `pending_approval_id` (so a task genuinely left
`APPROVAL_PENDING` — see below — can have that specific request
re-checked, not silently abandoned).

**A real behavior change this priority required**: Phase 16/17.1
always collapsed a genuinely-pending (no `ApprovalGate` wired,
awaiting an external `grant()`/`deny()`) approval straight to
`REQUIRES_HUMAN` within the same synchronous call, because nothing
could ever come back to check it again. Resume-in-place needed a task
to actually be resumable *from* `APPROVAL_PENDING`, so
`ExecutiveRuntime` now leaves it there — genuinely persisted, via
`ApprovalManager`'s new optional `memory=` durability (see below) — and
only collapses to `REQUIRES_HUMAN` once the request is actually
`denied`/`expired`. No existing test depended on the old collapse-on-
pending behavior; this is a strict improvement, not a breaking change
covered up.

**`ApprovalManager(..., memory=None)`** — optional, the same additive
pattern as everywhere else in Priority 17. Omitted: `ApprovalRequest`s
live only in an in-process dict, exactly as before (lost on restart).
`ExecutiveRuntime` always supplies it (it already requires a `memory`),
so a pending or decided approval survives a restart and is visible to
a completely different `ApprovalManager` instance querying the same
store — proven in `test_risk_and_approval.py::
TestApprovalManagerDurability` and end-to-end in
`test_resume.py::TestResumeInterruptedApproval`.

**Durable checkpoints**: `self._session.save(task)` is called at
exactly three points — right after a `Plan` is created (state
`PLANNING`), right after an `ApprovalRequest` is created (state
`APPROVAL_PENDING`), and right before delegation starts (state
`EXECUTING`). Everything before the first checkpoint
(`RECEIVED`/`UNDERSTANDING`/`CONTEXT_LOADING`) is pure, synchronous,
side-effect-free computation with nothing persisted mid-way — a crash
that early means the request was never durably received; resubmit it
via `handle_event()`. `resume()` is itself idempotent: calling it on an
already-`COMPLETED` (or otherwise terminal) task, or on one in
`REQUIRES_HUMAN`, returns the task unchanged rather than reprocessing
it.

**A real, previously-latent bug this priority found and fixed**:
`DelegationEngine`, when given its own `approval_manager=`,
independently re-checks approval for every non-LOW-risk step — useful
standalone (`test_delegation.py`), but redundant when driven through
`ExecutiveRuntime`, which already fully gates the task-level risk
decision before `EXECUTING` is ever reached (every `PlanStep`'s
`risk_level` is assigned from the same task-level `classify_risk()`
call). Wiring the same `ApprovalManager` into both created a *second*,
independent `ApprovalRequest` per step whose id was never surfaced
anywhere a human could grant it. This was invisible in Phase 16/17.1,
where `DELEGATING` was never reached with a genuinely-pending,
ungated task-level approval — but `resume()` can now legitimately carry
a task-level-granted approval through to `DELEGATING`, where the
orphaned per-step request would have wrongly denied it. Fixed by no
longer passing `approval_manager=` into `ExecutiveRuntime`'s internal
`DelegationEngine`; caught by actually running the resume scenario
end-to-end, not by inspection.

**What's NOT built**: resuming *within* `UNDERSTANDING`/
`CONTEXT_LOADING`/`PLANNING` at sub-step granularity — those phases are
fast, synchronous, and side-effect-free, so a crash there is handled
by simply resubmitting the request, not by finer-grained checkpointing.
Automatic re-driving of `REQUIRES_HUMAN` tasks once a human acts — a
deployment's own code calls `resume()` (or the lower-level
`StateMachine`/`ApprovalManager` APIs directly) after the human
decision is made; there is no polling loop that notices a
`REQUIRES_HUMAN` task became actionable on its own. No distributed
coordination if multiple processes might try to `resume()` the same
task concurrently — see Priority 17.4.

# Concurrency Model (Priority 17.4, ADR-0024)

**Status: IMPLEMENTED** for single-process thread-safety;
**explicitly NOT** cross-process/distributed. Full detail in
CONTRACT.md §17 — summary here:

**Ordering guarantee**: two calls racing the *same* task id, the same
delegation idempotency key, or the same approval request id are
serialized — one completes before the other's critical section begins.
Different task ids / keys / request ids run fully concurrently; Layla
never serializes unrelated work.

**What's locked**: `ExecutionTracker` (the real race:
`begin()`'s check-then-act, closed via a non-persisted
`claimed_this_call` marker so a concurrent observer of a just-created
record is distinguishable from its creator), `ApprovalManager`
(`grant()`/`deny()`/`check()`), `SessionManager` (the shared index),
`AuditLogger` (the shared per-scope sequence/index), `Scheduler`
(heap/jobs/callbacks — a job's own callback runs outside the lock),
and `ExecutiveRuntime` (one lock per task id, spanning the *entire*
`_advance()` call including `resume()`'s reload — this is the one
deliberately coarse lock in the set, because loading *before* the lock
would let a second racing `resume()` work off a stale snapshot).

**A bounded, documented exception to three "locked" frameworks**: this
priority also added narrow, additive locks to `core/`'s `EventBus`,
`memory-factory`'s `FileMemoryPolicy`/`SQLiteMemoryPolicy`, and
`mcp-factory`'s `MetricsCollector` — each framework's own full
pre-existing test suite still passes unmodified (core 47/47,
memory-factory 24/24, mcp-factory 70/70). `FileMemoryPolicy`'s fix in
particular closes a real, silent data-loss bug (concurrent `remember()`
calls to different keys in the same kind file could lose one entirely
via a whole-file load-mutate-save race) — not a theoretical concern.
`SQLiteMemoryPolicy` previously couldn't be used cross-thread at all
(`check_same_thread=True` by default); it now can be.

**A real, previously-undiscovered bug this priority found**:
`ExecutionTracker.begin()`'s original get-or-create was a genuine
check-then-act race — two threads could both observe "no record for
this key" and both create one, defeating the exact guarantee Priority
17.2 exists to provide. Closed with a lock plus a `claimed_this_call`
marker (see `execution.py`); `delegation.py`'s
`_CLAIMED_NON_TERMINAL_STATES` now includes `EXEC_REQUESTED`.

**What's NOT built**: cross-process/distributed coordination (no
distributed lock, no multi-worker-safe file locking — two separate OS
processes can still race); a deeper audit of
`UniversalToolRegistry`/rate-limit enforcement beyond `MetricsCollector`;
`Orchestrator`/`ChiefDomainAgent`/`InMemoryMemoryPolicy` were audited
and found already safe (read-only shared state / single atomic dict
ops respectively), so nothing was changed there. See
`layla/python/tests/test_concurrency.py` for the real,
`threading.Thread`-based proof behind every claim above.

# Controlled Live Integration Validation (Priority 17.5, ADR-0025)

**Status: infrastructure IMPLEMENTED; live run NOT PERFORMED** (no
credentials were available in the environment this was built in — see
below, stated plainly rather than glossed over).
`layla/python/tests/test_live_anthropic_integration.py` is one
deliberate, narrow exception to this platform's otherwise-universal
offline-testing discipline: gated `@unittest.skipUnless(LIVE_TEST_MODE=1
and a real ANTHROPIC_API_KEY)`, it validates the *full* path
`ExecutiveRuntime.handle_event()` → `Planner` → `DelegationEngine` → a
real `ChiefDomainAgent` → a real `avishkar_router.Router` → the real
`AnthropicProvider` → the live Anthropic Messages API → `ResultValidator`
→ `ExecutiveSynthesizer`. See CONTRACT.md §18 and
`docs/live-integration-guide.md` for exact execution instructions.

**Safeguards**: fixed to `claude-haiku-4-5` (cheapest catalog model),
`max_tokens=32`, one trivial fixed prompt, and an explicit `$0.01` cost
ceiling the test itself asserts against. The task is phrased read-only/
LOW-risk — it never reaches a write-classified delegation, never
triggers an approval gate, never invokes a tool/channel adapter. No
email, message, financial operation, or destructive action of any kind
happens anywhere in this test.

**Observability**: `avishkar_router`'s `CompletionResponse`/
`ProviderResponse` gained an additive `request_id` field (populated by
`AnthropicProvider` from the live response's own `.id`), and Layla's
own `DelegationRecord` gained an additive `cost_usd` field — closing
the last gap in Router's already-real cost/latency/token tracking
(`Router.route()` computed and logged/published those since Phase 2).

**What's honestly NOT verified**: a real, successful live call against
the Anthropic API. The skip path (missing credentials → skipped, not
faked) was verified; the live path itself was not exercised, because
no `ANTHROPIC_API_KEY` was available when this priority was built. Do
not read "the infrastructure exists" as "it was proven to work end to
end against the real API" — those are different claims, and only the
first one is true here. Whoever runs it first with a real key should
record the actual result in `docs/live-integration-guide.md`.

# Personal Model (Mission Layla Part 1, ADR-0026)

**Status: IMPLEMENTED.** `PersonalModel` (`personal_model.py`) is
Layla's continuously-evolving model of the person she works for —
identity, preferences, goals, decision patterns, work patterns,
communication style, project context, relationships, behavioral
patterns, personal knowledge, life events, habits, long-term
objectives. Not a second memory system: every fact is a namespaced key
(`personal:{category}:{key}`) inside the same `LaylaMemoryPolicy` every
other Layla component already uses, following the same index-key
pattern `SessionManager`/`AuditLogger` already established.

**Contradiction handling is a real, enforced code path**: `set()`
refuses to silently overwrite an existing, *different* value —
`PersonalFactContradictionError` unless the caller passes
`resolve="overwrite"`/`resolve="ignore"` explicitly, or uses
`correct(..., reason=...)` (a reasoned, always-succeeding overwrite,
delegating to `LaylaMemoryPolicy.correct()` verbatim). Writing the same
value twice is always a no-op — idempotent, matching every other
write-path in this codebase.

**Privacy, by construction, not by convention**: no category ships
with seed/default/example data of any kind — every fact is written
only by an explicit runtime call. `SENSITIVE_CATEGORIES`
(`relationships`, `behavioral_patterns`) additionally require
`confirmed=True` on every write, and `summary()` (what
`ContextBuilder` folds into every task's prompt context) never
includes their content verbatim — only the category name and a count.
This is a deliberate structural difference from GENESIS (the external
codebase audited during this mission's planning phase, see
`docs/mission-layla-1-plan.md`), which hardcodes a specific real
person's name, family members, and health conditions directly in
versioned source as default values — `PersonalModel` contains zero
GENESIS code and zero GENESIS data; only the general shape of one
pattern (a sensitive-layer confirmation gate) was judged worth reusing,
reimplemented here from scratch.

**Integration is entirely additive**: `ExecutiveRuntime(...,
personal_model=None)` / `ContextBuilder.build(..., personal_model=None)`
— omitted, behavior is unchanged (every prior test still passes
unmodified). Supplied, every task's `context["personal_model_summary"]`
carries a redacted digest.

**What's NOT built**: no UI/onboarding flow for populating facts (a
deployment writes them via `PersonalModel.set()` directly — e.g. from a
settings screen, a chat-based "remember that..." command, or a batch
import); no automatic fact extraction from conversation (Life OS's
finance/health modules and any "Layla learns preferences from
behavior" capability are explicitly future work, not this mission —
see `docs/mission-layla-1-plan.md` §22).

# Proactive Intelligence & Persistent-Runtime Orchestration (Mission Layla Parts 2 and 11, ADR-0026)

**Status: IMPLEMENTED.** `ProactiveEngine` (`proactive.py`) answers
"should Layla act without being asked" (Part 2) — and in this
architecture, that decision *is* what drives Layla's
SLEEP → EVENT → WAKE → ... → SLEEP persistent-runtime cycle (Part 11):
a `Scheduler`/`run_forever()` tick is the EVENT, `evaluate()` is
WAKE+CONTEXT+DECIDE, and the emitted actions are ACT (or a deliberate
non-act). No LLM is called merely to check "did anything change" —
every built-in evaluator inspects real, already-recorded state
(`SessionManager`/`AuditLogger`) via cheap Python; only an `ACTION_ACT`
trigger ever causes a real `handle_event()` (and therefore a real
LLM/agent) call.

**Action levels**: `IGNORE` (not even audited — never spam, never
accumulate noise), `OBSERVE` (recorded via `AuditLogger`, never
surfaced), `SUGGEST`/`ASK` (a `Notification`, never an autonomous side
effect), `ACT` (drives the *full* `handle_event()` pipeline — risk,
approval, delegation, everything — never a shortcut), `URGENTLY_ALERT`
(a `CRITICAL` `Notification`).

**Two built-in evaluators, both evidence-only**: a task stuck in
`REQUIRES_HUMAN` past a configurable age (`SUGGEST` → `URGENTLY_ALERT`);
a task with repeated delegation failures in its own audit history
(`OBSERVE` → `SUGGEST`). **Neither ever reaches `ACT`** — a deliberate
choice: "looks stuck" or "failed repeatedly" are reasons for a human to
look, not evidence strong enough to justify autonomous action.
Genuine `ACT`-level behavior requires a caller-supplied
`extra_evaluators` entry built for a specific, well-understood scenario
(see `layla/examples/personal_model_and_proactive_scenario.py` for a
worked one). This mirrors the one thing GENESIS's own
`proactive_engine.py`/`environment_prediction/` got right (real
trigger conditions from real state) while deliberately avoiding what
its `core/prediction/*.py` got wrong — this mission's own forensic
audit confirmed those return hardcoded literal dicts regardless of
input; `ProactiveTrigger` can never be constructed with a fabricated
confidence or prediction, only what its evaluator actually observed.

**Fails closed for Layla's own actions, not just a human's**: if
`authorization` is wired on the runtime and no `proactive_session_id`
was supplied, an `ACT` trigger's `handle_event()` call raises
`UnauthenticatedError`, caught and recorded as
`layla.proactive.act_failed` — never silently bypassed. A deployment
that wants real autonomous action must explicitly issue and supply a
session scoped for Layla's own use, the same as it would for any other
caller.

**Integration is entirely additive**: `ExecutiveRuntime(...,
enable_proactive=False)` (default) — `.proactive` is `None`, zero
behavior change. `enable_proactive=True` — the runtime builds its own
`ProactiveEngine` internally (avoiding a construction-order
chicken-and-egg problem: the engine's callback binds to the runtime's
own `handle_event`), and `run_forever()` calls `.evaluate()` every
tick, right after `Scheduler.tick()`.

**What's NOT built**: real event/schedule/goal/deadline/opportunity/
external-signal detectors (Part 2's full list) — only the two
evidence-based built-ins above exist; everything else requires a
caller-supplied evaluator today, and building genuinely reliable ones
for goals/deadlines/opportunities is real, dedicated future work, not
fabricated here to check a box (Mission Layla Part 26, "no fake
completion"). No async/background execution model — a slow `ACT`
callback delays the next scheduler tick until it returns, a known
limitation of this runtime's synchronous, thread-based (not
async-based) design.

# Mission Layla Continuation — Parts 3–27 (ADR-0027)

Following the Foundation-tier work above, Mission Layla continued
autonomously through the full remaining dependency order. Full detail
in CONTRACT.md §21–30 and ADR-0027; summary here.

**Real, fully-working components** (Prediction, Skills, Learning Loop,
Life OS, Knowledge Graph, a second Channel adapter, Business
Intelligence, an Executive Dashboard aggregator):
- **`PredictionEngine`** (`prediction.py`, Part 3) — every `Prediction`
  carries evidence and a genuinely computed confidence (a real ratio
  over `SessionManager`/`AuditLogger` history), never a hardcoded
  literal.
- **`SkillRegistry`** (`skills.py`, Part 12) — `CANDIDATE ->
  EVALUATING -> APPROVED|REJECTED -> RETIRED`, evaluated via
  `avishkar_evaluation`'s real `run_suite()`/`passes_threshold()` —
  `status` only ever becomes `APPROVED` as the observable result of a
  real evaluation, directly avoiding the exact bug this mission's
  forensic audit found in the external codebase it studied (a
  `learned` flag never actually set anywhere).
- **`LearningLoop`** (`learning.py`, Part 13) — real pattern extraction
  over completed-task history proposes `SkillRegistry` candidates;
  never self-approves, never touches source code.
- **`LifeOS`** (`life_os.py`, Part 4) — a thin domain layer over
  `PersonalModel`, extending its categories with `schedule`/`tasks`/
  `finance`/`health`/`travel`/`appointments`/`reminders` (`finance`/
  `health` are `SENSITIVE_CATEGORIES`); real filtering/sorting for
  upcoming appointments and due reminders.
- **`LaylaKnowledgeGraph`** (`knowledge_graph.py`, Part 5) — a real,
  minimal, from-scratch graph engine (typed nodes/edges, real BFS/
  shortest-path, referential integrity enforced), zero seed data —
  additive alongside Avishkar's existing vector-search Knowledge
  Framework, not a duplicate.
- **`WhatsAppChannelAdapter`** (`channels/whatsapp_adapter.py`, Part 9)
  — a second real `ProtocolAdapter`, the exact `EmailChannelAdapter`
  ADAPTER READY pattern. Routing across channels remains
  `UniversalToolRegistry`'s job (Phase 4) — no second router built.
- **`BusinessIntelligenceEngine`** (`business_intelligence.py`, Part
  26) — real task/cost/success-rate aggregation over `AuditLogger`
  history; surfaced and fixed a real gap where delegation audit
  records never carried `cost_usd`.
- **`ExecutiveDashboard`** (`executive_dashboard.py`, Parts 23/27) — a
  thin real aggregator over every Foundation-tier component's own
  `summary()`, not a new cognitive layer (`ExecutiveRuntime` already is
  that). Parts 24 (Multi-Agent Supervision) and 25 (Project Management)
  are already satisfied by `Orchestrator`/`DelegationEngine`/`Planner`
  and `ProjectStore` — not rebuilt.

**Contract/integration-boundary-only components** (Voice, Vision, OCR,
Spatial Intelligence, Environmental Awareness, Browser/Computer
Control, Application Control, Android/ADB, IoT, Sensors, Robotics,
Home Assistant, MQTT — Parts 6–8, 15–17, 21):
- **`PerceptionEngine`** (`perception.py`) — zero registered capture
  sources by default; `observe(source)` on an unconfigured source
  raises `PerceptionSourceNotConfiguredError` (the same ADAPTER READY
  pattern). Never a background capture daemon.
- **`EmbodimentController`** (`embodiment.py`) — `request()` computes
  risk via Layla's own real `risk.classify_risk()` and enforces
  `ApprovalManager` *before* any executor is looked up — structural,
  not name-matched, closing the exact bug class (a tool-naming
  mismatch silently disabling a safety gate) this mission's forensic
  audit found in the external codebase it studied. Zero executors
  registered by default.

**Why contract-only for this second group, explicitly**: this
mission's own Part-1 forensic audit (`docs/mission-layla-1-plan.md`)
found real, working code for every one of these capabilities in the
external codebase it studied — and found that same codebase's safety
gates for exactly these capabilities comprehensively non-functional
(shell exec, filesystem delete, browser automation, and ADB were all
either ungated or explicitly allowed by its own `permissions.json`,
due to a tool-naming mismatch that silently disabled its governor).
Building an equally-capable but *actually* safe backend for any of
these is dedicated, multi-day security-engineering work, not
compressible into this pass — per the mission directive's own explicit
fallback instruction, a real, tested, structurally-gated contract was
built instead of either skipping these capabilities or faking a
backend.

# Voice Subsystem (Directive D, Part I, ADR-0028)

Mic → `MicrophoneFrameSource` → `VoiceActivityDetector` →
`SpeechToTextProvider` → **the unchanged `ExecutiveRuntime.handle_event()`
pipeline** → `TextToSpeechProvider` → `SpeakerSink`. See CONTRACT.md §31
for the full contract. Explicit status per component (Directive D's
required GREEN/YELLOW/RED classification):

| Component | Status | Notes |
|---|---|---|
| `EnergyVAD` | 🟢 GREEN | Real numpy RMS-threshold VAD, adaptive noise floor + `calibrate()`; 9/9 tests real and passing. |
| `FasterWhisperSTT` | 🟢 GREEN | Real local CTranslate2 Whisper inference, no API key. Genuine synthesize→transcribe round trip verified (`test_voice_stt.py`). |
| `Pyttsx3TTS` | 🟢 GREEN | Real local SAPI5 synthesis, no API key; 4/4 tests real and passing. |
| Device enumeration (`list_input_devices`/`list_output_devices`) | 🟢 GREEN | Real `sounddevice`/PortAudio query against this machine's actual hardware. |
| `VoiceSession` orchestration | 🟢 GREEN | Real segmentation/routing/response-synthesis/interruption logic, 18/18 tests real and passing against injected fakes. |
| `MicrophoneFrameSource` / `SpeakerSink` live capture/playback | 🟡 YELLOW | Real, hardware-backed code, construction-validated against this machine's real devices — but never exercised end-to-end by the automated suite (opening a live mic non-interactively during an unattended run is treated as a real-world action requiring a deliberate trigger, same as embodiment/IoT). Requires a real deployment to actually run a live session. |
| `OpenAIWhisperAPISTT` / `OpenAITTSProvider` | 🟡 YELLOW | Real HTTP clients against OpenAI's real endpoints — ADAPTER READY, no `OPENAI_API_KEY` configured in this environment, so not live-tested. |
| Full-duplex acoustic barge-in (detecting speech *while* Layla is speaking) | 🔴 NOT BUILT | Only explicit stop-phrase / external `request_stop()` interruption is implemented; true overlapping-speech detection needs echo cancellation, out of scope for this pass. |

Install the optional extra to use any real provider:
```bash
pip install -e "layla/python[voice]"
```
The cognitive core has zero dependency on any voice package; only
constructing a concrete `FasterWhisperSTT`/`Pyttsx3TTS`/
`MicrophoneFrameSource`/etc. pulls one in.

# Vision / OCR / Spatial Intelligence (Directive D, Part II, ADR-0029)

Camera/Screen → Capture → Vision Pipeline (OCR/Detection/Spatial
Analysis) → structured `PerceptionObservation` → Layla Context →
Decision. See CONTRACT.md §32. Nothing in `avishkar_layla.vision`
calls a tool/executor/`handle_event()` — every function returns data
that must pass through Layla's existing decision/risk architecture,
per Directive D's explicit requirement.

| Component | Status | Notes |
|---|---|---|
| `distance`/`overlaps`/`iou`/`relative_position`/`nearest` (spatial.py) | 🟢 GREEN | Real, dependency-free geometry; 13/13 tests real and passing. |
| `extract_text` (ocr.py) | 🟢 GREEN | Real Tesseract OCR — the binary was installed on this machine during this pass (`winget install UB-Mannheim.TesseractOCR`) specifically so this could be genuinely GREEN rather than ADAPTER READY. Real word-level boxes/confidence from `image_to_data`, verified against a synthetically-rendered (not live-captured) test image. |
| `detect_template` (detection.py) | 🟢 GREEN | Real `cv2.matchTemplate`; 4/4 tests real and passing against synthetic textured images. Found and documented a real caveat: flat/solid-color regions can produce spurious matches with `TM_CCOEFF_NORMED` — the tests use textured images specifically because of this. |
| `capture_screen` (screen_capture.py) | 🟡 YELLOW | Real, `PIL.ImageGrab`-backed, confirmed working against this machine's actual 1366×768 display during development — but never called against the live screen by the automated suite (same non-interactive-capture consent boundary as the microphone); error-handling tested via an injectable `_grab_fn` seam instead. |
| `screen_capture_source`/`screen_ocr_source` (perception_adapters.py) | 🟢 GREEN | Real wiring into `PerceptionEngine`'s existing contract; 3/3 tests real and passing against a monkeypatched capture layer. |
| General-purpose visual/scene classification ("what is this") | 🔴 NOT BUILT | No trained object/scene classifier is bundled or fabricated this pass — `detect_template()` answers "does this known image appear, and where," not open-vocabulary recognition. |
| Perception fusion beyond structured observations | 🔴 NOT BUILT | `PerceptionObservation` already carries source/confidence/timestamp/permissions/retention per observation; a dedicated multi-observation fusion/reasoning layer is real future work. |

Install the optional extra to use real OCR/detection:
```bash
pip install -e "layla/python[vision]"
```
`pytesseract` is a wrapper around the real `tesseract` binary, which is
a separate OS-level install (not a pip package) — see
`vision/ocr.py`'s `OCRNotAvailableError` message for install links per
platform.

# Computer Control (Directive D, Part III, ADR-0030)

Real `EmbodimentExecutor`s registered into the existing
`EmbodimentController` (§28/ADR-0027) — the risk/approval gate is
unchanged and unweakened: every executor here only ever runs after
`request()` has already computed risk and secured approval. See
CONTRACT.md §34.

| Component | Status | Notes |
|---|---|---|
| `BrowserExecutor` — navigate/click/type/get_text/screenshot | 🟢 GREEN | Real Playwright, headless Chromium. Genuinely drives a real browser session; 8/8 unit tests + 3/3 integration tests (through the real `EmbodimentController` gate) real and passing, exercised against `data:` URLs (no network dependency, no live site). |
| `ComputerControlExecutor` — shell execution | 🟢 GREEN | Real `subprocess.run`, allowlist-gated (empty allowlist = nothing runs). Real commands genuinely executed and verified in tests. |
| `ComputerControlExecutor` — file operations | 🟢 GREEN | Real, confined to a `workspace_root` via a real path-containment check; tested with real path-traversal attack strings. |
| `ComputerControlExecutor` — GUI control (mouse/keyboard/clipboard/screenshot) | 🟡 YELLOW | Real `pyautogui`/`pyperclip` code behind an injectable `_gui` seam — never invoked against this machine's real cursor/keyboard by the automated suite (would hijack a real desktop session non-interactively); dispatch logic tested via an injected fake. Requires a real deployment (and a human aware a session is running) to exercise live. |
| Application launching / window management | 🔴 NOT BUILT (this pass) | `psutil`/`pygetwindow` are available in this environment and were confirmed working for read-only enumeration, but a real launch/window-management executor wasn't wired to `EmbodimentController` yet — tracked as remaining Part III scope. |

**Security finding from this pass's own tests** (not merely asserted —
`test_embodiment_real_executors_integration.py` proved it both ways):
`EMBODIMENT_BROWSER` is not in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES`, so plain navigation classifies LOW
via the real text classifier and completes without approval; only
action text that itself reads as dangerous is gated. This is existing,
deliberate ADR-0027 behavior (browser risk is genuinely
content-dependent — visiting a URL is not inherently as dangerous as
running a shell command), but a deployment wanting every browser
action gated regardless of wording should explicitly add
`EMBODIMENT_BROWSER` to that frozenset. Documented here rather than
silently assumed either way.

Install the optional extra and browser binary:
```bash
pip install -e "layla/python[computer_control]"
playwright install chromium
```

# Android / ADB (Directive D, Part IV)

`ADBExecutor` (executors/adb_executor.py) — REAL CODE / ADAPTER READY.
See CONTRACT.md §35.

| Component | Status | Notes |
|---|---|---|
| `is_adb_available()` | 🟢 GREEN | Real `shutil.which()` check — reports `False` on this machine (no `adb` binary installed), verified by a real (not fabricated) test. |
| `ADBExecutor` dispatch logic | 🟢 GREEN | 13/13 tests real and passing via an injected `_run` seam — every action's real `adb` command line construction is verified. |
| Live device interaction | 🟡 YELLOW | No `adb` binary and no connected Android device exist in this environment — genuinely untested live. `ADBExecutor()` with no injected `_run` raises `ADBNotAvailableError` ("ADAPTER READY") rather than fabricating a result, confirmed by a real test on this machine. |

Registered for `EMBODIMENT_ADB`, already in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES` — every action requires approval
regardless of wording. `shell` has its own fail-closed allowlist, same
as `ComputerControlExecutor.run_shell`.

# Communication Channels (Directive D, Part V, ADR-0032)

Every channel is a real `avishkar_integration.ProtocolAdapter` routed
through the existing `UniversalToolRegistry`/`ToolRuntime` — no second
router. See CONTRACT.md §36.

| Channel | Adapter status | Transport status | Notes |
|---|---|---|---|
| Email | 🟢 GREEN | 🟢 GREEN | `SMTPEmailTransport` — real `smtplib`/STARTTLS/MIME, genuinely speaks SMTP to a real local test server this suite runs itself (its own fixture, not a mock). |
| WhatsApp | 🟢 GREEN | 🟡 YELLOW | `WhatsAppCloudAPITransport` — real HTTP client, real network call against Meta's actual Graph API confirmed correctly rejecting an invalid token; no live Business account configured here. |
| Telegram | 🟢 GREEN (NEW) | 🟡 YELLOW | `TelegramBotAPITransport` — real HTTP client, real-rejection-tested against Telegram's actual Bot API. |
| Slack | 🟢 GREEN (NEW) | 🟡 YELLOW | `SlackWebAPITransport` — real HTTP client; correctly reads Slack's real `ok:false` body (Slack always returns HTTP 200), real-rejection-tested. |
| Discord | 🟢 GREEN (NEW) | 🟡 YELLOW | `DiscordBotAPITransport` — real HTTP client, real-rejection-tested against Discord's actual Bot REST API. |
| SMS | 🟢 GREEN (NEW) | 🟡 YELLOW | `TwilioSMSTransport` — real, installed `twilio` SDK, real-rejection-tested against Twilio's actual API. |
| LinkedIn, Google (Gmail/Calendar), Zoom | 🔴 NOT BUILT | 🔴 NOT BUILT | Explicitly not built this pass — reported as a real gap, not silently skipped. |

"Adapter status" GREEN means the `ProtocolAdapter`/registry-routing/
approval-gating machinery is real and tested (it was already GREEN for
Email/WhatsApp from ADR-0027; Telegram/Slack/Discord/SMS are new this
pass). "Transport status" reflects whether an actual external account
is live-verified — all six are real, credentialed-at-call-time code;
none has a live account configured in *this* environment, so YELLOW is
honest even where the transport code itself is proven correct via a
real network rejection test.

**Send-approval policy**: not a new mechanism. Every channel `invoke()`
is reached only via a real tool call; when routed through
`ExecutiveRuntime`, `classify_risk()`/`ApprovalManager` already gate
DELEGATING before any channel is called (§4/§11) — Directive D's "Layla
must NOT automatically send arbitrary messages simply because an LLM
generated them" is satisfied by the existing pipeline, unmodified.

Install the optional extra:
```bash
pip install -e "layla/python[channels]"
```

# Environmental Awareness (Directive D, Part VI, ADR-0033)

Sensor → Event → EventBus → Perception/Context → Layla → Decision →
Action, built entirely on existing components (`avishkar_core.EventBus`,
`Scheduler`, `ProactiveEngine`) — no new event system. See CONTRACT.md
§38.

| Component | Status | Notes |
|---|---|---|
| `IdleTimeSensor`/`BatterySensor`/`SystemLoadSensor` | 🟢 GREEN | Real local OS/process state (Win32 `GetLastInputInfo`, `psutil`) — this machine genuinely has a battery, so `BatterySensor` was verified for real, not merely code-reviewed. |
| `NetworkConnectivitySensor` | 🟢 GREEN | A real socket-level TCP reachability probe (not just an interface-up flag) — verified against a real reachable host and a real, deliberately non-routable one. |
| `SensorMonitor` | 🟢 GREEN | Real threshold/change-detection logic against a real `EventBus`; 6/6 tests real and passing — confirms the "no polling flood" behavior (unchanged readings never publish). |
| `EnvironmentalEventBuffer`/`EnvironmentalChangeEvaluator` | 🟢 GREEN | Real `EventBus` subscription/filtering and a real, retry-storm-safe `ProactiveEngine` evaluator; 8/8 tests real and passing, including that the same event is never re-triggered. |
| Full chain integration | 🟢 GREEN | `test_environment_end_to_end.py` proves a scripted sensor change flows through every real component to a real `ProactiveTrigger`, entirely without an LLM call. |
| Camera/microphone-based environmental signals | — | Already covered by `voice`/`vision` (Directive D Parts I/II) — deliberately not duplicated here. |

No wiring exists yet to automatically register `EnvironmentalChangeEvaluator`
into a running `ExecutiveRuntime`'s `ProactiveEngine` by default — a
deployment opts in explicitly via `ProactiveEngine(extra_evaluators=(evaluator,))`,
matching every other evaluator's wiring (ADR-0026).

# Home Assistant (Directive D, Part VII, ADR-0034)

`HomeAssistantExecutor` (executors/home_assistant_executor.py) — REAL
CODE / ADAPTER READY. See CONTRACT.md §40.

| Component | Status | Notes |
|---|---|---|
| `list_states`/`get_state`/`call_service`/`get_config` dispatch | 🟢 GREEN | Real HTTP client against Home Assistant's actual REST API shape; 9/9 tests real and passing against a real, minimal, in-repo HTTP server fixture this suite runs itself (real Bearer-token checking, real 401 handling, real JSON parsing). |
| `EmbodimentController` gating | 🟢 GREEN | 2/2 real end-to-end tests: an approved `list_states` call reaches the real fixture server; a denied `call_service` call never does. `EMBODIMENT_HOME_ASSISTANT` is already in embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` — every action requires approval regardless of wording. |
| Live device/entity interaction | 🟡 YELLOW | No live Home Assistant instance exists in this environment — genuinely untested live. `HomeAssistantExecutor` raises `HomeAssistantNotConfiguredError` ("ADAPTER READY") rather than fabricating a result when no base URL/token is configured. |

# MQTT (Directive D, Part VIII, ADR-0035)

`MQTTBridge` (mqtt/client.py) + `MQTTExecutor` (executors/mqtt_executor.py)
— REAL. See CONTRACT.md §42.

| Component | Status | Notes |
|---|---|---|
| Connect/authenticate/TLS/publish/subscribe/reconnect | 🟢 GREEN | Real `paho-mqtt` client (VERSION2 callback API), genuinely verified against a real, minimal, in-repo MQTT 3.1.1 broker this suite runs itself — real CONNECT/CONNACK with real username/password auth, real PUBLISH, real SUBSCRIBE/SUBACK, real retained-message delivery, real PINGREQ/PINGRESP. 14/14 tests real and passing, including a genuine end-to-end publish → real broker → real `on_message` callback → real `EventBus` event. |
| EventBus event translation | 🟢 GREEN | Every inbound MQTT message becomes a real `avishkar_core.EventBus.publish("layla.mqtt.<topic>", ...)` call — no separate MQTT event queue. |
| Topic allowlist gating | 🟢 GREEN | Real, fail-closed publish/subscribe allowlists with real MQTT `+`/`#` wildcard matching (`topic_matches()`), verified against real MQTT topic-matching semantics. |
| `EmbodimentController` gating | 🟢 GREEN | 2/2 real end-to-end tests: an approved publish reaches the real broker fixture; a denied one never does. **`EMBODIMENT_MQTT` was added to embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` this pass** — a real security enhancement found while implementing this part (an MQTT publish is routinely how real physical devices are commanded, the same reasoning already applied to Home Assistant/ADB/Computer Control/Robotics). |
| Live external broker | — | Not applicable — GREEN was achieved via a real in-repo broker fixture rather than requiring a live external broker. This sandboxed environment's outbound network access was confirmed allowlisted to specific known API hosts (Meta/Telegram/Slack/Discord/Twilio, Part V) — `test.mosquitto.org:1883` was confirmed unreachable during this pass, so no live public broker was used or claimed. |

Install the optional extra:
```bash
pip install -e "layla/python[mqtt]"
```

# Robotics / Embodiment (Directive D, Part IX, ADR-0036)

`RobotSafetyController` (robotics/controller.py) — a real safety layer
built entirely on existing components (`EmbodimentController`,
`risk.classify_risk`, `ApprovalManager`, `AuditLogger`); no new
cognitive/risk/event framework. See CONTRACT.md §44.

| Component | Status | Notes |
|---|---|---|
| Emergency stop / human override | 🟢 GREEN | A real software latch, set before the real driver's own stop call — verified even a driver whose `emergency_stop()` itself raises still leaves the latch engaged. Checked first on every call, ahead of any `EmbodimentController` approval. |
| Timeout / cancellation | 🟢 GREEN | Real `threading.Thread.join(timeout=...)` against a real slow fake driver — a genuinely late result is never read or applied. |
| Fail-safe behavior | 🟢 GREEN | Any timeout or driver exception triggers a real fail-safe callback AND latches the emergency stop before the error propagates — verified further actions are refused until an explicit `reset_emergency_stop()`. |
| State verification / audit trail | 🟢 GREEN | Real `get_state()` queried and recorded after every action via the existing `AuditLogger`. |
| `EmbodimentController` gating | 🟢 GREEN | 3/3 real end-to-end tests: approved reaches the real driver; denied never does; an emergency-stopped controller refuses even an approved request. `EMBODIMENT_ROBOTICS` has been in `_DEFAULT_HIGH_RISK_CAPABILITIES` since ADR-0027. |
| Physical robot hardware | 🟡 YELLOW / ADAPTER READY | No physical robot exists in this environment. `RobotDriver` (`execute()`/`get_state()`/`emergency_stop()`) is the documented boundary a deployment implements for its real platform (ROS, a proprietary API, etc.) — all of the safety logic above is real and independent of which driver is plugged in. |

# Personal Executive Communication (Directive D, Part X, ADR-0037)

`executive_communication.py` implements Directive D's own worked
example: "Avishkar has not responded to this person for 7 days → …→
Generate draft → Risk assessment → Approval policy → Send → Record
outcome → Update memory." Calendar/Meetings/Appointments/Reminders are
already real, existing `LifeOS` functionality — not rebuilt. See
CONTRACT.md §46.

| Component | Status | Notes |
|---|---|---|
| `StaleRelationshipEvaluator` | 🟢 GREEN | Real relationship lookup (`PersonalModel`), real days-since-contact computation, real `do_not_disturb`/custom-eligibility filtering, real retry-storm-safe dedup. 8/8 tests real and passing. |
| `record_contact_outcome()` | 🟢 GREEN | Real `PersonalModel.correct()` call, provenance-tracked; 3/3 tests real and passing, including that an unknown contact is refused rather than silently created. |
| Full chain integration | 🟢 GREEN | A real `ProactiveEngine` end-to-end test: a stale `PersonalModel` relationship → a real `ACTION_SUGGEST` trigger → a real `Notification`. |
| Draft generation / send | — | Deliberately NOT reimplemented here — this is exactly what the unchanged `ExecutiveRuntime.handle_event()` pipeline already does (real risk classification, real approval, real Chief-Domain-Agent drafting, real Part V channel sending) when a suggestion is acted on. Duplicating it here would violate "Avishkar OS remains the foundation." |

# 24/7 Operation (Directive D, Part XI, ADR-0038)

Real hardening of the existing `Scheduler`/`ExecutiveRuntime.run_forever()`
loop — no new persistent-runtime mechanism. See CONTRACT.md §48.

| Component | Status | Notes |
|---|---|---|
| Scheduler failure isolation | 🟢 GREEN | A real gap found by reading `tick()`'s own code: a job callback was called with NO exception handling — one failing job could crash the entire 24/7 loop. Now isolated unconditionally; 6/6 real tests, including that a raising job never blocks other due jobs in the same tick. |
| Scheduler dead-letter | 🟢 GREEN | Optional `max_consecutive_failures` — a real `cancel()` after a job keeps failing, not merely a flag; 3/3 real tests, including that the default (`None`) preserves prior retry-forever behavior exactly. |
| Graceful shutdown | 🟢 GREEN | A real `threading.Event`-based `request_shutdown()`, checked at the top of every `run_forever()` iteration; a real `layla.runtime.run_forever_stopped` audit record via the existing `AuditLogger`. |
| Heartbeat / liveness | 🟢 GREEN | `last_tick_at`/`is_alive(max_staleness_seconds=...)` — real, using the runtime's own injectable clock. |
| Operational health report | 🟢 GREEN | `operational_health()` — real liveness, real incomplete-task count (`SessionManager`), real scheduler pending/dead-letter state when a scheduler is configured. Deliberately excludes CPU/memory/battery (real, but behind `environment.sensors`'s optional `psutil` dependency — combined externally, not force-coupled into `runtime.py`). |
| Crash recovery | — | Already real via Priority 17.3's resume-in-place (`SessionManager.list_incomplete()`/`ExecutiveRuntime.resume()`) — not rebuilt. |

# Durable Execution (Directive D, Part XII, ADR-0039)

Most of "durable execution" is already real, existing functionality
(checkpoints/resume-in-place, idempotency keys, retry policies, an
execution journal) — not rebuilt. `task_lease.py` adds the two items
Directive D Part XII names that nothing existing covered: task
ownership and stale-task recovery. See CONTRACT.md §50.

| Component | Status | Notes |
|---|---|---|
| `TaskLeaseManager` acquire/renew/release | 🟢 GREEN | Real, thread-safe (lock-guarded), durable across a restart (persisted via `LaylaMemoryPolicy`). 10/10 real tests. |
| Real concurrency proof | 🟢 GREEN | A genuine multi-thread test: 20 real threads race to acquire the same lease — exactly one wins, verified. |
| Stale-lease detection | 🟢 GREEN | `is_stale()`/`find_stale_leases()` — real expiry comparison against the manager's own injectable clock; intended real usage: `find_stale_leases(t.id for t in session_manager.list_incomplete())` on process startup. |
| Multi-process distributed locking | 🔴 NOT CLAIMED | Explicitly documented scope limit, not a gap papered over: true atomicity across *multiple concurrent OS processes* depends on the underlying `LaylaMemoryPolicy` backend's own guarantees (`remember()` is an unconditional write, not a compare-and-swap), which this layer does not itself provide. Correctly scoped for the deployment model Directive D actually describes (one active process, restarted after a crash) — not oversold as a distributed lock service. |

# Security Hardening (Directive D, Part XIII, ADR-0040)

A fresh review across authentication/authorization/secrets/injection/
exfiltration/SSRF. Most of Directive D's list is already real, existing
coverage from earlier phases (`AuthorizationManager`, `ApprovalManager`,
`PersonalModel`'s `SENSITIVE_CATEGORIES`, `test_adversarial.py`,
repository-wide secret scanning after every commit this whole
Directive D pass). See CONTRACT.md §52.

| Finding | Status | Notes |
|---|---|---|
| Browser SSRF to cloud metadata endpoints | 🔴→🟢 FOUND AND FIXED | `EMBODIMENT_BROWSER` is LOW-risk-by-default for harmless-*sounding* text (ADR-0030) — a `navigate` to `http://169.254.169.254/latest/meta-data/iam/security-credentials/` previously reached Playwright with **zero approval gate**, since "navigate to a URL" isn't dangerous-sounding text. On a real cloud VM with an attached IAM role, this could have exfiltrated real, live credentials. Fixed with a real, hard block (`executors/ssrf_guard.py`) refusing navigation to private/loopback/link-local/reserved addresses and known metadata hostnames — verified end to end: a real `navigate` call to `169.254.169.254` is confirmed refused before Playwright opens a connection. |
| Repository-wide secret scan | 🟢 CLEAN | `scan_repository_for_secrets("layla")` — 3 matches, all pre-existing, known, intentional test fixtures (AWS's own documented example key). Zero real secrets, zero new findings across this entire Directive D pass (Parts I–XIII). |
| Prompt injection / hostile tool responses / unauthorized capability requests | 🟢 Already real | `test_adversarial.py`, unmodified this pass — continues passing. |
| Sensitive memory / PII / health / financial data | 🟢 Already real | `PersonalModel.SENSITIVE_CATEGORIES` requires `confirmed=True` for `relationships`/`behavioral_patterns`/`finance`/`health` — unmodified, used correctly by every new component this pass that touches personal data (e.g. `executive_communication.py`'s relationship writes). |

# Observability (Directive D, Part XIV, ADR-0041)

`build_production_health_report()` — a single-call aggregation of
already-real, separate capabilities (`AuditLogger`, `Router` cost/
request tracking, `BusinessIntelligenceEngine`,
`ExecutiveRuntime.operational_health()`), not a new metrics/tracing
system. See CONTRACT.md §54.

| Component | Status | Notes |
|---|---|---|
| `build_production_health_report()` | 🟢 GREEN | Real aggregation: operational health, real per-status delegation totals, a real computed failure rate, and (when given) `BusinessIntelligenceEngine`'s own real cost/success-rate report folded in unmodified. 7/7 tests real and passing. |
| Real bug found and fixed by this module's own first test run | 🟢 disclosed | `AuditLogger.history()` is scoped per `task_id` — an initial draft's global, no-argument call silently saw only `"system"`-scoped events and missed every real per-task delegation record. Fixed to mirror `BusinessIntelligenceEngine`'s own established real pattern (enumerate tasks via `SessionManager.list_all()`, then query each task's own history) rather than introducing a second, different way of answering the same question. |
| EventBus queue-depth/throughput metrics | 🔴 NOT COVERED | Honestly disclosed, not fabricated: `avishkar_core.EventBus` exposes no statistics at its current abstraction layer; adding this would mean modifying core/'s locked `EventBus`, out of scope for this pass. |
| Memory-backend operation latency | 🔴 NOT COVERED | Same reasoning — `LaylaMemoryPolicy`/its backend expose no per-operation timing; a future pass would need a new cross-cutting instrumentation layer, not built here. |

# Cost/Resource Management (Directive D, Part XV, ADR-0042)

Rate limits and retry policy per external tool were already real,
existing capability (`avishkar_integration`'s `RateLimit`/
`RetryPolicy`) — reused as-is, not duplicated. The real, previously-
open gap was in `ProactiveEngine.evaluate()`: no cap at all on how
many `ACTION_ACT`-level triggers it would dispatch (i.e. actually
invoke `act_callback`, which is always wired to a real `handle_event()`
call) in a single tick. See CONTRACT.md §56.

| Component | Status | Notes |
|---|---|---|
| `ProactiveEngine.evaluate()` ACT-trigger throttle | 🟢→🟢 FOUND AND FIXED | Real, previously-open "runaway autonomous loop" gap: a custom evaluator returning many ACT triggers in one tick had zero dispatch limit, meaning unboundedly many real LLM calls per single `Scheduler` tick. Fixed with an additive `max_act_triggers_per_evaluate` parameter (default `5`, conservative but confirmed via inspection to change no existing evaluator's behavior); triggers beyond the cap are recorded via the real `AuditLogger` as `layla.proactive.act_throttled`, never silently dropped. `None` restores the prior unbounded behavior explicitly. 5/5 new tests real and passing, all 14 tests in the file passing. |
| External tool rate limits / retry policy | 🟢 Already real | `avishkar_integration.RateLimit`/`RetryPolicy` — unmodified, judged sufficient reuse for this directive's "rate limits" ask; no new infrastructure built. |
| Token/task cost budgets (hard spend ceilings) | 🔴 NOT COVERED | Honestly disclosed: `Router` already tracks real per-request `cost_usd` (Priority 17.5) and `BusinessIntelligenceEngine` already aggregates it, but no component enforces a hard budget ceiling that blocks further execution once crossed — future work, not built this pass. |
| Concurrency limits (max simultaneous in-flight tasks) | 🔴 NOT COVERED | Honestly disclosed: `Scheduler`/`ExecutiveRuntime` place no explicit ceiling on concurrently EXECUTING tasks; not built this pass. |

# Production Deployment (Directive D, Part XVII, ADR-0044)

Config/secrets loading reuses `avishkar_core.Config`'s real, existing
layered precedence (defaults < file < env < overrides) — not
duplicated. See CONTRACT.md §60 and [OPERATIONS.md](./OPERATIONS.md)
for the full runbook (startup/shutdown/health/backup/restore/disaster
recovery/rollback/DEVELOPMENT→TEST→STAGING→PRODUCTION profiles).

| Component | Status | Notes |
|---|---|---|
| `HealthServer` (`/health`, `/health/report`) | 🟢 GREEN | Real stdlib `http.server.ThreadingHTTPServer`. 9 tests make real HTTP requests against a real running server on an OS-assigned ephemeral port — not mocked. |
| Graceful shutdown (`install_graceful_shutdown()`) | 🟢 GREEN | Real `signal.signal()` registration for SIGINT/SIGTERM, calling the already-real `ExecutiveRuntime.request_shutdown()`. Tested via an injectable `_signal_module` seam rather than raising a real OS signal at the test process. |
| Backup/restore (`backup_data_directory()`/`restore_data_directory()`) | 🟢 GREEN | Real `shutil.copytree` to/from a timestamped directory, operating on `FileMemoryPolicy`'s real 4 JSON files. 3 tests prove a real round-trip (write → backup → corrupt → restore → verify) against real files, not a simulation. |
| `layla/deploy/run_production.py` (reference entrypoint) | 🟢 GREEN, deliberately generic | Real, smoke-tested end to end: constructs a real `ExecutiveRuntime`/`Orchestrator`/`ChiefDomainAgent`, runs a real tick, serves a real `/health` request. One generic "general-agent" domain — actual production agent rosters are application-specific, not decided by this platform layer. Falls back to `MockProvider` with a loud real log warning if `ANTHROPIC_API_KEY` is unset (still a real, runnable process — useful for smoke-testing the deployment boundary independent of a live LLM credential). |
| `layla/Dockerfile` (base runtime image) | 🟡 WRITTEN, NOT BUILD-VERIFIED | Mirrors the exact `PYTHONPATH` composition every test/example script in this repo already uses. Honestly disclosed external-dependency gap: no Docker daemon is running in this sandboxed environment (CLI present, daemon not started), so `docker build`/`docker run` were not verified end to end here — the underlying Python entrypoint IS real and smoke-tested independently. |
| Monitoring/alerting push integration (Prometheus/Datadog/PagerDuty, etc.) | 🔴 NOT COVERED | `/health/report` is real, structured JSON meant to be polled/scraped by an external system — no push-based integration is built. Honestly disclosed future work. |

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
`SessionManager`'s durable state means a restart can resume incomplete
tasks: call `sessions.list_incomplete()` on startup and `resume(task.id)`
each one (Priority 17.3, ADR-0023) — the supervisor's job is only to
restart the process, not to preserve state itself. A restart also
needs the *same* `execution_tracker=`/`memory=` backing store the
crashed process used (a `FileMemoryPolicy`/`SQLiteMemoryPolicy` at a
stable path, not `InMemoryMemoryPolicy`) or there is nothing to resume
from.

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

583 tests as of Directive D Part XVII (Production Deployment) (119
Phase 16 + 30 Priority 17.1 + 21 Priority 17.2 + 8 Priority 17.3 + 11
Priority 17.4 + 1 Priority 17.5 + 30 Mission Layla 1 [PersonalModel/
ProactiveEngine] + 82 Mission Layla continuation [Prediction/Skills/
LearningLoop/LifeOS/KnowledgeGraph/WhatsAppChannelAdapter/Perception/
Embodiment/BusinessIntelligence/ExecutiveDashboard] + 40 Directive D
Part I [EnergyVAD/device enumeration/Pyttsx3TTS/FasterWhisperSTT/
VoiceSession] + 28 Directive D Part II [spatial geometry/real OCR/real
template detection/screen capture DI/perception adapter wiring] + 34
Directive D Part III [real headless-browser automation/real shell
execution/real confined file operations/GUI dispatch via injected
fake/end-to-end EmbodimentController+executor integration] + 13
Directive D Part IV [real ADB availability check/ADB command dispatch
via injected fake/real ADAPTER READY error on this adb-less machine] +
29 Directive D Part V [real SMTP wire-protocol round trip against a
real local test server/real network-rejection tests against WhatsApp,
Telegram, Slack, Discord, and Twilio's actual APIs with deliberately
invalid credentials/adapter+registry routing for 4 new channels] + 20
Directive D Part VI [real local sensors/real EventBus threshold-based
publishing/real retry-storm-safe ProactiveEngine evaluator/full real
end-to-end chain integration] + 11 Directive D Part VII [real Home
Assistant REST API dispatch against a real local fixture server/
real end-to-end EmbodimentController approval gating] + 17 Directive D
Part VIII [real MQTT wire-protocol round trip against a real in-repo
MQTT 3.1.1 broker fixture/real topic-allowlist and wildcard matching/
real end-to-end EmbodimentController approval gating, including the
new EMBODIMENT_MQTT high-risk-by-default classification] + 14
Directive D Part IX [real enforced timeouts/real emergency-stop latch/
real fail-safe triggering/real state verification/real end-to-end
EmbodimentController approval gating, all without physical hardware] +
11 Directive D Part X [real relationship-staleness detection/real
follow-up eligibility filtering/real retry-storm-safe dedup/real
outcome recording/full real ProactiveEngine end-to-end integration] +
21 Directive D Part XI [real scheduler failure isolation/real
dead-letter escalation/real graceful shutdown/real heartbeat-liveness/
real operational health aggregation] + 14 Directive D Part XII [real
thread-safe task-lease acquire/renew/release/real 20-thread concurrency
proof/real stale-lease detection] + 11 Directive D Part XIII [real
SSRF guard for private/loopback/link-local/metadata addresses/real
end-to-end refusal test against a live BrowserExecutor/repository-wide
secret scan] + 7 Directive D Part XIV [real production-health-report
aggregation/real per-task delegation-history discovery bug found and
fixed/real BusinessIntelligenceEngine integration] + 5 Directive D
Part XV [real ProactiveEngine ACT-trigger dispatch throttle/real
runaway-autonomous-loop resource-exhaustion gap found and fixed/real
AuditLogger-recorded throttling, never silently dropped] + 0 Directive
D Part XVI [testing taxonomy audit against all 74 existing test files
-- no new tests, no genuine gap found] + 9 Directive D Part XVII [real
HealthServer HTTP liveness/report endpoints against a real running
server/real injectable-signal-module graceful-shutdown wiring/real
FileMemoryPolicy backup-corrupt-restore round trip against real
files]), 581 running offline and
passing, 2 live/environment-gated and skipped by
default (`test_live_anthropic_integration.py` — see
`docs/live-integration-guide.md` to actually run it; plus one OCR
availability test that only runs on a machine WITHOUT tesseract
installed, correctly skipped on this one). One real, environment-load
test flake was observed and independently reproduced-clean in this
pass: `test_click_actually_changes_real_page_state` (a real Playwright
click against a real headless browser) exceeded its 15s timeout once
under heavy real CPU contention from this development machine's own,
actively-used Chrome tabs (21+ real `chrome.exe` processes observed at
the time) — re-run in isolation immediately after, it passed in 19s.
Not a code defect; disclosed here rather than silently re-run away.
Also this pass: `MQTTBridge`'s first real test run surfaced a genuine
bug (not a test artifact) — `paho-mqtt` 2.x's VERSION2 callback API
passes `on_connect` a real `ReasonCode` object, not a plain int;
`int(reason_code)` raised a real `TypeError`, caught immediately by
the test suite and fixed to use the real, documented `reason_code.is_failure`
property instead. Left in DECISIONS.md ADR-0035 as a concrete example
of a real defect a real test caught before commit, not merely claimed.
Via:
```bash
PYTHONPATH="core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;factories/evaluation-factory/python;factories/prompt-factory/python;factories/workflow-factory/python;layla/python" \
  python -m unittest discover -s layla/python/tests
```
(`evaluation-factory`/`prompt-factory`/`workflow-factory` are new to
this PYTHONPATH string as of `SkillRegistry`'s real
`avishkar_evaluation` integration — already a declared
`layla/python/pyproject.toml` dependency, just not previously imported
at package-init time.) Voice tests need the optional `voice` extra
(`pip install -e "layla/python[voice]"`) installed to run at all —
`test_voice_stt.py` downloads the real `faster-whisper` "tiny.en"
model from Hugging Face on first run (cached after) and skips with an
explicit reason if that download is impossible in a given environment,
rather than failing the whole suite or fabricating a pass.

**Gotcha for test-file-to-test-file imports** (found by this pass's
own full-suite run, not merely anticipated): `discover -s
layla/python/tests` adds that directory to `sys.path` and imports each
file as a bare top-level module (`test_mqtt_bridge`, not
`layla.python.tests.test_mqtt_bridge`), even though `tests/` has an
`__init__.py`. A package-relative import between two test files (e.g.
`test_mqtt_bridge.py` importing its `_minimal_mqtt_broker.py` fixture
via `from ._minimal_mqtt_broker import ...`) works when a test is run
by its full dotted path but fails under the real `discover` command
with "attempted relative import with no known parent package." Use a
plain top-level import (`from _minimal_mqtt_broker import ...`)
instead for any shared test fixture module.
Categories: unit (state machine, memory policy, risk, scheduler,
execution/idempotency classification), contract (every component's own
dataclass/error shape), integration (delegation through a real
`Orchestrator`, the full `ExecutiveRuntime` loop, execution-tracker
wiring), adversarial (`test_adversarial.py` — prompt injection, hostile
tool responses, unauthorized capability requests, duplicate events,
memory corruption attempts, restart-during-execution, approval
expiration, contradictory instructions), idempotency/crash-recovery
(`test_execution.py`, `test_delegation_idempotency.py`,
`test_runtime_idempotency.py` — duplicate retries, timeout-to-UNKNOWN,
resolve_unknown, cross-instance crash recovery via `FileMemoryPolicy`),
resume-in-place (`test_resume.py` — resuming a completed/unknown/
`REQUIRES_HUMAN` task, crash-mid-delegation recovery, interrupted-
approval recovery across three separate `ExecutiveRuntime` instances;
`test_risk_and_approval.py::TestApprovalManagerDurability` for
`ApprovalManager`'s own cross-instance persistence), and one
deterministic end-to-end fixture (`test_end_to_end_scenario.py`)
matching Part IX.

## Test Taxonomy Audit (Directive D, Part XVI, ADR-0043)

An audit — not a new test-writing pass — confirming every category
Directive D Part XVI names (unit/integration/e2e/security/failure-
recovery/concurrency/scheduler/channel/tool-execution/memory/
perception/computer-control/embodiment-safety) already has genuine,
non-trivial coverage across all 574 tests. Full category-by-category
file/test-count breakdown: CONTRACT.md §58. Summary:

| Category | Status | Thinnest point (disclosed) |
|---|---|---|
| Unit / Integration / Security / Failure-recovery / Concurrency / Scheduler / Channel / Tool-execution / Memory / Perception / Computer-control / Embodiment-safety | 🟢 all covered | — |
| E2E | 🟢 covered, honestly thinnest | Only 2 unittest e2e tests + 2 narrated runnable examples — appropriate given e2e tests are inherently slower/broader, but the smallest category by file count. |

**Deterministic fakes vs. real tests** (consolidated in one place for
the first time, not new information — each was already disclosed in
its own Directive D part): real live network calls with deliberately-
invalid credentials (Slack/Discord/Telegram/Twilio/WhatsApp Cloud API
subsets), one real live LLM test (`test_live_anthropic_integration.py`,
skipped by default), real local-fixture wire-protocol tests (SMTP,
MQTT 3.1.1, Home Assistant REST — genuine protocol implementations,
not mocks), one real hardware-adjacent DI-gated test (`test_adb_executor.py`,
confirmed on this actual adb-less machine), and — for everything else —
deterministic fakes (in-memory stores, injectable clocks, injected fake
`_grab_fn`/`_gui`/`client_factory` seams). See CONTRACT.md §58 for the
full breakdown.

No genuine gap was found against Directive D's named taxonomy.

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
- **A delegation fails with `"...is already UNKNOWN from a prior
  attempt..."`** — a previous call for that same `{task_id}:{step.id}`
  timed out on a non-`READ` operation and its outcome was never
  resolved. Call `ExecutionTracker.resolve_unknown(key, EXEC_COMPLETED
  | EXEC_FAILED, note=...)` after confirming the real-world outcome
  out-of-band (e.g. checking the provider's own dashboard/logs), then
  retry — see CONTRACT.md §15. This is Layla correctly refusing to
  guess, not a bug.
- **`IdempotencyConflictError`** — the same idempotency key was reused
  for a different operation than its original request (a key-collision
  bug, since `DelegationEngine` derives keys from `task_id`/`step.id`,
  which are random per task/plan). Check for accidental task-id reuse
  before retrying.
- **`resume()` keeps returning the task unchanged, still
  `APPROVAL_PENDING`** — nobody has called `grant()`/`deny()` on
  `task.pending_approval_id` yet. This is correct, not a bug —
  `resume()` only re-checks a decision, it never makes one.
- **`resume()` re-runs every delegated step instead of skipping
  completed ones** — `execution_tracker` wasn't passed to the
  `ExecutiveRuntime` that's calling `resume()`, or it's a *different*
  `ExecutionTracker`/`memory` than the one the crashed process used.
  Idempotent skipping is Priority 17.2's `ExecutionTracker`, not a
  property of `resume()` itself — see Idempotency & Side-Effect Safety,
  above.

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
