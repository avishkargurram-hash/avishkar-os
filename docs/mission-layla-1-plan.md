# MISSION LAYLA 1 — IMPLEMENTATION PLAN

**Status: PLANNING ONLY. NOTHING HAS BEEN IMPLEMENTED, MODIFIED, COPIED, MOVED, OR COMMITTED.**
Date: 2026-08-11. Sources: 6 parallel read-only forensic audits of `C:\Users\Administrator\Documents\robot_ai` (git remote `avishkarroopi/Genesis-AI`, the confirmed canonical/live GENESIS tree — `Desktop/Genesis` is an untracked, non-git copy and was not used), cross-referenced against the full Avishkar OS / Layla codebase at `C:\Users\Administrator\Desktop\Avishkar Labs\Avishkar-OS` (built across Phases 1–17 in this same session).

---

## 1. Executive Summary

GENESIS is a large (712 tracked files, ~47 `core/` subsystems), ambitiously-scoped personal-AI/robot codebase with a self-certifying README claiming "100% production ready, no stubs, no TODOs, no mocks." **That claim is false**, verified by reading actual source, not documentation, across all 20 requested capability areas. The honest picture:

- **A large fraction of GENESIS's most interesting-sounding subsystems are dead code** — real Python, never called from `core/system.py`'s actual boot sequence (`core/digital_twin/`, `core/user_model.py`, `core/personal_knowledge/`, most of `core/founder/`'s learning chain, `core/founder/blackbox_authority.py`, `core/agi/unified_core.py`'s vetting, and more).
- **A meaningful fraction of what does run is hardcoded fake output** dressed as computed intelligence — `core/prediction/{behavior_model,future_task_predictor,opportunity_detector,risk_detector}.py` return fixed literal dicts regardless of input; `core/digital_twin/decision_pattern_model.py` and `behavior_simulator.py` are explicitly self-labeled stubs; `core/research/synthetic_research.py` always returns `"validated", confidence: 0.88`.
- **GENESIS's own security model is comprehensively broken for exactly the dangerous capabilities it claims to gate.** A naming mismatch between the safety governor's hardcoded dangerous-tool list and the real tool-registry IDs means the "Existential Sovereignty Lock" never actually fires for real shell-exec/filesystem-delete/browser-automation/ADB tool calls. `permissions.json` explicitly *allows* filesystem delete, mouse/keyboard takeover, and browser automation. An identity-verification check on the highest-stakes voice commands fails open due to a type-mismatch bug. A "temporary test" backdoor in `core/genesis_voice.py` lets any local file write inject unauthenticated commands, bypassing wake-word and identity checks entirely.
- **Real, specific personal PII (full names, spouse's name, children's names and DOBs, health conditions, psychological states) is hardcoded in plaintext source and persisted unencrypted with zero access control**, contradicting the modules' own "Locked Vault" framing.
- **`.env` with real API key values is committed to git history and present on the public/private GitHub remote right now** — an active incident, flagged separately above, outside this plan's scope.
- **A small number of genuinely well-engineered subsystems exist**: `core/knowledge_graph.py` (real BFS/pathfinding graph engine), `core/auth/` (Fernet-encrypted token store, real circuit breaker, real OAuth clients for 6+ providers), `core/identity_system/` (real InsightFace face-recognition, gracefully degrading), `core/agi/master_intelligence.py` (a real, if redundant-with-Layla, rule-based governor), `core/genesis_voice.py`/`core/voice_agent.py` (real STT/TTS pipeline), `core/services/communication/*` (real WhatsApp/Telegram/Slack/Discord/Twilio/Email REST clients), and `core/user_model.py` (the cleanest personal-behavior-modeling module found — real computed confidence, real persistence, no hardcoded PII — but dead code today).

**Recommendation, stated plainly up front**: the honest scope of what's safe, valuable, and fits a 3-hour execution window is **much narrower** than the directive's 22-part investigation surface. Most of Parts H–N and O's higher-risk pieces (Voice, Vision, Computer Control, IoT, Self-improvement, Channels) should be **FUTURE**, not MUST/SHOULD, specifically because GENESIS's own implementations demonstrate that bolting a security layer on after the fact fails silently in exactly the ways that matter — porting the *capability* would require building it from scratch through Avishkar's real Capability Resolver → Risk Classifier → Authorization → Approval chain, which is itself a multi-day effort per capability, not a 3-hour port. What genuinely fits this window is: (a) a real Personal Model layer for Layla, built fresh using Avishkar's own Memory/Identity contracts and *informed* by GENESIS's design patterns (confidence scoring, graceful degradation, sensitive-layer confirmation gating) rather than its code; (b) a light Proactive Intelligence layer built on Layla's existing Scheduler/EventBus; (c) documentation of everything else as reference material for later phases.

---

## 2. Current Layla Architecture (as of Phase 17 completion, this session)

Layla (`layla/`) is Avishkar OS's Personal Executive Intelligence layer — a third platform-wide capability alongside `core/`/`router/` (ADR-0020), composed entirely from other frameworks' public contracts, never duplicating them. Current state: 190 tests (189 passing, 1 deliberately skipped), 25 modules.

```
ExecutiveRuntime (handle_event() / resume() -> one shared _advance() pipeline)
  |-- StateMachine        RECEIVED -> UNDERSTANDING -> CONTEXT_LOADING -> PLANNING ->
  |                        [APPROVAL_PENDING ->] EXECUTING -> DELEGATING -> WAITING ->
  |                        VERIFYING -> SYNTHESIZING -> COMPLETED (+ FAILED/CANCELLED/
  |                        TIMEOUT/BLOCKED/REQUIRES_HUMAN)
  |-- IntentInterpreter    real keyword classifier
  |-- ContextBuilder       composes memory + knowledge lookups into task.context
  |-- LaylaMemoryPolicy    wraps avishkar_agent.MemoryPolicy (4 locked kinds: short_term/
  |                        long_term/episodic/semantic); refuses secret-shaped values
  |-- CapabilityResolver / Planner   whole-word capability inference -> PlanStep list
  |-- risk.classify_risk()   LOW/MEDIUM/HIGH, pattern-based
  |-- ApprovalManager      auto-grant LOW, ApprovalGate for MEDIUM/HIGH, or genuinely
  |                        persisted APPROVAL_PENDING awaiting grant()/deny()
  |-- AuthorizationManager  Principal/Role/Session, least-privilege capability
  |                        enforcement, structural anti-self-escalation for agent
  |                        principals, self-approval always denied
  |-- DelegationEngine     typed wrapper around avishkar_agent.Orchestrator, retry via
  |     |                  RetryPolicy, timeout-aware
  |     `-- ExecutionTracker  idempotency: classify_operation() READ/WRITE/HIGH_RISK,
  |                        fail-closed default; a COMPLETED step never re-invoked;
  |                        an in-flight/uncertain non-READ step refuses concurrent retry
  |-- ResultValidator / ConflictResolver / ExecutiveSynthesizer
  |-- Scheduler            min-heap, persistent-if-backed-by-durable-memory, thread-safe
  |-- AuditLogger / SessionManager   full trace, resume-in-place from any checkpoint
  |-- NotificationManager / HealthMonitor
  `-- channels/EmailChannelAdapter  ADAPTER READY (real code, no live transport configured)
```

Concurrency (Priority 17.4): per-component locks, real races found and fixed via actual `threading`-based tests, single-process only (no cross-process coordination). Live integration (Priority 17.5): real `AnthropicProvider` exists, one opt-in env-gated live test exists, never executed against a real key in this session (no credentials available).

**Explicitly does not have today**: any notion of a "Personal Model" (identity/preferences/goals/decision-patterns/relationships as a first-class object), any proactive/opportunistic behavior (Layla only ever acts in response to `handle_event()`/`resume()` being called — there is no autonomous "should I act right now" loop), voice/vision/computer-control/IoT of any kind, a knowledge graph (Layla's Knowledge framework is vector-search-based, from Phase 6), and no "skill learning" concept.

---

## 3. GENESIS Capability Inventory (ground truth from the 6 audits)

| Capability | Real? | Wired/reachable? | Headline finding |
|---|---|---|---|
| Digital Twin (`core/founder/founder_digital_twin.py`) | Yes, real rule-based multi-source prediction w/ reasoning trace | Reachable via `master_intelligence` telemetry | Good design pattern (self-reported confidence + reasoning trace), GENESIS-specific data sources |
| Digital Twin (`core/digital_twin/`) | Mixed — real event bookkeeping, but `get_context_prediction()` hardcodes `confidence: 0.85` | **Dead** — zero callers | Competing/duplicate concept vs. `founder_digital_twin.py`, name collision on `get_founder_twin()` |
| `core/user_model.py` (top-level) | **Yes, genuinely real** — computed confidence, real habit/preference inference, real JSON persistence | **Dead** — zero callers | Best-engineered personal-modeling module in the whole codebase; no PII baked in |
| Digital Founder Genome (`digital_founder_genome.py`) | Yes, real access-control pattern (sensitive layers require `founder_confirmed=True`) | Reachable via `founder_digital_twin.py` | Good governance *pattern*; underlying data is hardcoded real PII (health conditions, psych state) |
| Proactive Intelligence (`core/autonomous/proactive_engine.py`) | Real but thin — 2 hardcoded triggers, 2 hardcoded goal strings | Live (polled every 300s) | Real, safe, minimal — genuinely portable *pattern* |
| Prediction (`core/prediction/*.py`, 4 files) | **Fake** — 100% hardcoded literal dict returns, ignoring input | Live (wired to event bus) | Do not use — dressed-up stubs |
| Environment Prediction (`core/environment_prediction/`) | **Yes, genuinely real** — trend detection, linear trajectory extrapolation, frequency counting | Unclear reachability (not confirmed live) | Best "prediction" code found; still crude (hand-picked confidence constants) |
| Autonomous Scheduler (`core/autonomous/scheduler.py`) | Real persistence/dedup/retry/history; **broken execution** — hands raw text to a function that only parses pre-formatted LLM tool-call tags | Live | Persistence *design* is good; execution wiring is a real bug — do not port as-is |
| Life OS (`core/life_os/`) | **Fake** — 5 files are 12-line event-fire stubs, zero persistence | Live (fires events nobody stores) | Directly contradicts README's "no stubs" claim |
| Knowledge Graph (`core/knowledge_graph.py`) | **Yes, genuinely real** — typed nodes/edges w/ confidence+provenance, adjacency BFS, shortest-path, atomic JSON persistence | Live | Real, ~500 lines, no external graph DB dependency; **but** seeds real hardcoded PII (owner's email) and has zero access control on the personal data it stores |
| Voice (`core/genesis_voice.py`, `core/voice_agent.py`) | **Yes, genuinely real** — real VAD, faster-whisper STT, pyttsx3/Piper TTS, real lip-sync | Live | Mature; but ships an unconditional file-polling command-injection backdoor (`text_injector`) |
| Vision (`core/vision/yolo_detector.py`, `llava_reasoner.py`) | **Yes, genuinely real** — real camera+YOLO, real local TinyLLaVA inference | Live | Real; `screen_capture_service.py` is a continuous unattended screen-recording daemon (privacy-relevant) |
| Computer Control (`body/screen_control.py`, `core/tools/action_tool.py`, `core/services/action/*`) | **Yes, real capability, catastrophically under-gated** | Live, LLM-tool-reachable | See §17 — the single most severe finding of the audit |
| IoT (`core/services/iot/home_assistant_service.py`, `core/listeners/mqtt_listener.py`) | Real | Live | Real physical-device control (lights/locks) gated only by token presence; unauthenticated webhook listener on `0.0.0.0:8124` |
| Self-improvement / Self-modification (`core/self_dev/self_dev_engine.py`) | **Yes, real, and dangerous** — full write→sandbox→apply→reload pipeline, zero human-approval gate inside the function | **Dead** — the one integration point is broken (`ImportError` swallowed) | Must never be ported or referenced as a template, regardless of reachability |
| Self-improvement (observational, `core/self_improvement/*`) | Real but purely advisory — logs/publishes suggestions, nothing consumes them to change behavior | Live | Safe, but the name overstates the capability — no closed learning loop |
| Skills (`core/skills/*.py`) | **Fake** — 5 files, hardcoded fake-success strings | Live | "Opened browser at {url}" does not open a browser |
| Skills (`core/skill_engine.py`) | Real dispatcher, but `learned: bool` is **never set `True` anywhere in the repo** | Live | No actual skill-learning loop despite the data model implying one |
| Persistent Runtime | **Yes, genuinely real and mostly event-driven** — real `asyncio.PriorityQueue` EventBus, `CognitiveModule` base class defaults to `poll_interval=0.0`, real FastAPI/uvicorn server | Live | Good architecture reference; several independent fixed-interval polls coexist (60s/30s/5s), not naive "call-LLM-every-tick" |
| Channels (`core/services/communication/*`) | **Yes, genuinely real** — WhatsApp, Telegram, Slack, Discord, Twilio, Email/SendGrid, real HMAC-verified webhooks (mostly) | Live | Real REST clients; one file (`hubspot_webhooks.py`) has its signature-check `raise` commented out — silent auth bypass |
| Auth infra (`core/auth/`) | **Yes, the most mature subsystem found** — Fernet encryption, SQLite token store, real circuit breaker, real OAuth flows for 6 providers | Live | Best candidate for a REFERENCE/PORT-WITH-MODIFICATION decision of anything in GENESIS |
| Security (`core/security/*`) | Mixed — `reactive_guard.py`/`response_contract.py`/`approval_gate.py` genuinely solid; `permission_guard.py`/`owner_only_access.py`/`execution_guard.py`/`safe_mode.py` naive-to-broken | Live | Do not treat any "security" claim in this codebase as true without independently verifying the specific function |

---

## 4. OpenClaw Capability Targets (design targets — not GENESIS-sourced)

Per Part O: persistent runtime without unnecessary LLM consumption, pluggable channels, continuous operation via SLEEP→EVENT→WAKE→UNDERSTAND→ACT→WAIT/SLEEP. **GENESIS's real EventBus + `CognitiveModule(poll_interval=0.0)` pattern is architecturally close to this target** — genuinely event-driven, not a naive loop — but it is GENESIS-specific code we will not port. Layla should acquire the *pattern* by building its own equivalent directly on `avishkar_core.EventBus` (already real, already hardened in Phase 17.4) plus `layla.scheduler.Scheduler` (already real, already hardened). No new capability needs to be invented here — Layla already has the primitives; what's missing is a *thin orchestration layer* that decides when to wake and call an LLM versus stay dormant. This is a genuinely small, safe addition.

## 5. Hermes Capability Targets (design targets — not GENESIS-sourced)

Per Part P: learning loop, persistent memory (canonical — already Layla's), reusable skills (versioned/evaluated/auditable), scheduled jobs (already Layla's, hardened in Phase 17), multi-platform operation. GENESIS's `core/skill_engine.py` demonstrates the *wrong* way to do this (a `learned` flag that's never set) — useful as a negative example, not a template. A real "skill" for Layla should be: a versioned `PlanStep` template + an evaluation record (reusing `avishkar_evaluation`'s already-real `QualityGate`/`EvalSuite`) + an audit trail (reusing `AuditLogger`) — i.e., built from Avishkar's own already-real components, not GENESIS's.

## 6. Capability Comparison

| Dimension | Avishkar/Layla today | GENESIS | Target after Mission Layla 1 |
|---|---|---|---|
| Risk/Approval/Authorization | Real, tested, fail-closed, structurally anti-escalation | Broken (naming-mismatch gate, fake vetting, weak-default fallbacks) | **Unchanged — Layla's stays authoritative** |
| Idempotency/Durable Execution | Real, tested, concurrency-hardened | Real persistence layer, broken execution wiring | **Unchanged — Layla's stays authoritative** |
| Personal Model | **None** | Scattered across 4+ non-integrated representations, real PII hardcoded | **New**: a real, minimal Personal Model built on Layla's own Memory contract |
| Proactive Intelligence | **None** (purely reactive) | Real but thin (2 triggers) | **New**: a minimal, Scheduler-driven proactive check, informed by GENESIS's trigger-pattern design |
| Knowledge Graph | Vector-search only (Phase 6) | Real, working, ~500-line graph engine | **Not this mission** — a genuine graph engine is a real multi-day effort; documented as future work |
| Voice/Vision/Computer Control/IoT | **None** | Real capability, catastrophically under-gated | **FUTURE**, explicitly deferred — see §17, §22 |
| Skills/Learning | **None** | Fake (stubs) or unused (`learned` never set) | **FUTURE** — build on `avishkar_evaluation`, not GENESIS |

---

## 7. Exact GENESIS Files Worth Using (as design reference, not code)

None are recommended for direct code copy (Category A, DIRECT ADAPT) — see §17/§18 for why. The following are worth reading as **design pattern references** (Category D):

1. `core/user_model.py` — habit/preference inference shape, computed-confidence pattern.
2. `core/founder/founder_digital_twin.py` — "always emit a reasoning trace + graceful degradation to `Insufficient data`" pattern.
3. `core/founder/digital_founder_genome.py` — sensitive-layer confirmation-gate pattern (`founder_confirmed=True` required to write health/financial/relationship data).
4. `core/environment_prediction/__init__.py` — real trend/trajectory computation shape (if a future phase builds real environmental awareness).
5. `core/autonomous/proactive_engine.py` — minimal trigger-condition shape (failure-streak + idle-timer), safely portable as a *pattern*, not code (its actual goal strings/thresholds are GENESIS-specific and trivial to reimplement fresh).
6. `core/auth/` (whole directory) — Fernet-encrypted token store + circuit-breaker pattern, worth a full read by whoever eventually builds Layla's own external-channel OAuth story (not this mission).
7. `core/agi/cognitive_module.py`'s throttle/kill-switch pattern — conceptually similar to what Layla would want for a proactive loop, though Layla should build its own using its own `Scheduler`/`EventBus`, not import this.

## 8. Exact GENESIS Files to Reject

Everything not listed in §7, with explicit call-outs:
- `core/self_dev/self_dev_engine.py` — **never reference, never port, never use as a template**, regardless of current unreachability (§1, §17).
- `core/prediction/{behavior_model,future_task_predictor,opportunity_detector,risk_detector}.py` — fake.
- `core/digital_twin/*`, `core/personal_knowledge/*` — dead code, and where not dead, contains fake confidence values.
- `core/skills/*.py` — fake.
- `body/screen_control.py`, `core/tools/action_tool.py`, `core/services/action/*.py`, `core/tools/mobile_tool.py`, `core/services/blackbox/automation.py` — real but catastrophically under-gated; reject as code, defer the *capability* to FUTURE with a from-scratch Avishkar-native design.
- `core/services/iot/*`, `core/listeners/ha_webhook_listener.py`, `core/listeners/mqtt_listener.py` — real but unauthenticated/under-gated.
- `core/founder/founder_profile_loader.py`, `founder_profile_schema.py`, `core/owner_system.py` — real hardcoded PII; reject outright, never touch, never copy even as "example data."
- `core/knowledge_graph.py` — good code, but its live data file contains real hardcoded PII with zero access control; if ever revisited, would need a from-scratch reimplementation with Layla's own memory/privacy policy wrapping it, not this file directly.
- `core/agi/master_intelligence.py`, `core/founder/blackbox_authority.py`, `core/ethical_layer/` — redundant with Layla's own risk/approval/authorization stack, which is more rigorously tested and fail-closed by construction (Phase 17.1); do not introduce a second, weaker parallel system.

## 9. Files to Adapt

**None.** Given the density of real security/privacy findings across every cluster audited, no GENESIS file meets the bar for direct or lightly-modified adaptation into a production platform this mission. This is a deliberate, considered recommendation, not an oversight — see §17/§18 for the reasoning.

## 10. Files to Reimplement (concept only)

- A Layla-native `PersonalModel` (informed by `core/user_model.py`'s shape: habits, preferences, computed confidence — reimplemented fresh against `LaylaMemoryPolicy`, no GENESIS code copied).
- A Layla-native minimal `ProactiveEngine` (informed by `core/autonomous/proactive_engine.py`'s trigger-condition shape — reimplemented fresh against `Scheduler`/`EventBus`).

## 11. Files to Reference Only (read for context, never touch again)

All of §3's "Real, genuinely engineered" rows not already covered: `core/auth/`, `core/knowledge_graph.py`, `core/genesis_voice.py`/`voice_agent.py`, `core/vision/yolo_detector.py`/`llava_reasoner.py`, `core/services/communication/*`, `core/security/reactive_guard.py`/`response_contract.py`/`approval_gate.py`. Useful for future phases' engineers to read before building the real (Avishkar-native) equivalent — never to import or copy.

## 12. Avishkar Components That Must Remain Authoritative

Per the directive's explicit list, restated as a commitment, none of these are touched by this mission: Core Engine, AI Router, Agent Framework, Chief Domain Agents, Universal Tool Registry, MCP, Memory Framework, Knowledge Framework, Workflow Framework, Evaluation, Security, Identity, Approval, Risk, Audit, Idempotency, Durable Execution. No `GenesisMemory`/`GenesisRouter`/`GenesisAgentManager`/`GenesisToolRegistry`/`GenesisEventBus` will be created.

## 13. Proposed Layla Architecture After Integration (this mission's scope only)

```
ExecutiveRuntime (unchanged)
  |-- ... all Phase 16/17 components (unchanged) ...
  |-- PersonalModel (NEW, layla/python/avishkar_layla/personal_model.py)
  |     -- wraps LaylaMemoryPolicy under a namespaced key scheme (long_term,
  |        "personal:{category}:{key}"), never a new memory system
  |     -- categories: identity, preferences, goals, decision_patterns,
  |        work_patterns, communication_style, project_context (relationships/
  |        behavioral_patterns explicitly deferred -- see SS22, they are the
  |        highest privacy-risk categories per the GENESIS audit's own findings)
  |     -- every write requires an explicit `confidence` and `provenance`
  |        (reusing MemoryRecord's existing fields -- no new schema)
  `-- ProactiveEngine (NEW, layla/python/avishkar_layla/proactive.py)
        -- optional constructor arg on ExecutiveRuntime, additive pattern
        -- Scheduler-driven tick (default 300s, injectable clock/interval)
        -- evaluates a small, explicit set of trigger conditions (repeated
           delegation failures via ExecutionTracker, task backlog via
           SessionManager.list_incomplete()) and calls handle_event() with a
           synthesized LOW-risk task input when a trigger fires -- reuses the
           entire existing pipeline, never bypasses risk/approval
```

## 14. New Modules Required

1. `layla/python/avishkar_layla/personal_model.py` — `PersonalModel` class, ~150-200 lines.
2. `layla/python/avishkar_layla/proactive.py` — `ProactiveEngine` class, ~100-150 lines.
3. `layla/python/tests/test_personal_model.py`, `test_proactive.py`.
4. `layla/examples/personal_model_scenario.py` (real, runnable demonstration, matching this repo's established pattern).

## 15. Modified Modules Required

1. `layla/python/avishkar_layla/runtime.py` — add optional `personal_model=`/`proactive_engine=` constructor params (additive, matching every Phase 17 precedent — omitted, zero behavior change).
2. `layla/python/avishkar_layla/__init__.py` — export new symbols.
3. `layla/CONTRACT.md` — new §20 documenting `PersonalModel`/`ProactiveEngine`.
4. `layla/README.md`, `ROADMAP.md`, `CHANGELOG.md`, `DECISIONS.md` (new ADR-0026) — per this repo's own established documentation discipline.

## 16. Migration Dependency Graph

```
LaylaMemoryPolicy (existing, unchanged)
        |
        v
PersonalModel (new) -----> consumed by -----> ContextBuilder (existing, optionally
        |                                       extended to include personal-model
        |                                       summary in task.context -- additive)
        v
ProactiveEngine (new) --> Scheduler (existing) --> ExecutiveRuntime.handle_event()
                                                    (existing, unmodified entry point)
```
No new external dependency. No change to any existing contract's required fields.

## 17. Security Risks

**From GENESIS (informing what NOT to build), ranked by severity, all confirmed by direct code reading, not assumption:**

1. **CRITICAL** — `core/services/blackbox/automation.py`: unrestricted `subprocess.run(caller_text, shell=True)`, LLM-tool-reachable, no gate.
2. **CRITICAL** — The GENESIS safety governor's dangerous-tool list uses names that don't match real tool-registry IDs — the entire "fail-closed" mechanism silently never fires for shell exec, filesystem delete, browser automation, ADB, process kill, mouse/keyboard control.
3. **CRITICAL** — `permissions.json` explicitly allows (not merely fails to block) filesystem delete, mouse/keyboard takeover, browser automation.
4. **HIGH** — Identity verification on high-stakes voice commands fails open due to a type-mismatch bug swallowed by a broad `except`.
5. **HIGH** — `body/screen_control.py`'s security gate is dead code (wrong import path, missing target function) — unconditionally bypassed.
6. **HIGH** — Unrestricted ADB shell execution to any connected/wireless Android device.
7. **HIGH** — Unrestricted filesystem delete including recursive `rmtree`.
8. **HIGH** — An unconditional command-injection backdoor in `core/genesis_voice.py` (`text_injector`), bypassing wake-word and identity checks.
9. **MEDIUM** — Real physical device control (locks/lights) via Home Assistant, gated only by token presence.
10. **MEDIUM** — Unauthenticated webhook listener on `0.0.0.0:8124`.
11. **MEDIUM** — `hubspot_webhooks.py`'s signature check is present but its enforcement (`raise`) is commented out — silent bypass.
12. **CONFIRMED INCIDENT** — `.env` with real API keys committed to git history, present on GitHub remote (flagged separately above, outside this plan).

**Implication for this mission**: zero of the above are introduced into Avishkar/Layla, because zero GENESIS code touching any of these paths is being adapted. The two new modules proposed (§13) touch only `LaylaMemoryPolicy` (already refuses secret-shaped values) and `Scheduler`/`handle_event()` (already risk/approval-gated) — no new attack surface.

## 18. Data/Privacy Risks

- GENESIS hardcodes real PII (names, DOBs, health conditions, psychological states) in versioned source and stores it unencrypted with zero access control, directly contradicting its own "Locked Vault" framing. **None of this data, or any code that touches it, will be read into, copied into, or referenced by Avishkar/Layla in any form.** I did not reproduce any of the actual PII values in this report or in the six agents' outputs beyond noting their *categories* (name, DOB, health condition types) — no names, no dates, no diagnoses were echoed.
- The new `PersonalModel` module (§13) is deliberately scoped to exclude the highest-risk categories the GENESIS audit flagged (relationships, detailed health/behavioral-pattern data) in this first mission — only `identity` (display name/role, non-sensitive), `preferences`, `goals`, `decision_patterns`, `work_patterns`, `communication_style`, `project_context` are in scope, and even those go through `LaylaMemoryPolicy`'s existing secret-scan refusal.
- No new persistence mechanism is created — `PersonalModel` is namespaced keys within Layla's existing, already-audited `long_term` memory kind.

## 19. Testing Strategy

Matching this repo's own established discipline (every Phase 16/17 priority): unit tests for `PersonalModel`/`ProactiveEngine` in isolation (DI'd fake clock/memory), contract tests (every new dataclass/field), integration tests (`ProactiveEngine` driving a real `ExecutiveRuntime.handle_event()` call end-to-end against a fake `Orchestrator`), regression (full existing 190-test Layla suite must still pass unmodified), a runnable example script. No live/network tests needed (nothing in this mission's scope touches an external system).

## 20. Implementation Sequence (if approved)

1. `PersonalModel` (read/write/list categories, secret-refusal reuse, tests) — foundation, no dependents yet.
2. `ProactiveEngine` (trigger evaluation, Scheduler wiring, tests) — depends on nothing new besides existing `Scheduler`/`SessionManager`/`ExecutionTracker`.
3. `ExecutiveRuntime` wiring (optional constructor params) + `ContextBuilder` extension (optional personal-model summary injection).
4. Runnable example (`personal_model_scenario.py`).
5. Documentation (CONTRACT.md §20, README.md, ADR-0026, ROADMAP.md, CHANGELOG.md).
6. Full regression + commit (only after your approval, per your own gate).

## 21. Three-Hour Prioritization

Given ~3 hours of execution time and the security findings above, the realistic, honest allocation:
- **Hour 1**: `PersonalModel` — implementation + tests.
- **Hour 2**: `ProactiveEngine` — implementation + tests + `ExecutiveRuntime` wiring.
- **Hour 3**: Example script, documentation (CONTRACT.md/README.md/ADR/ROADMAP/CHANGELOG), full regression, commit.

Nothing else from the directive's 16-area list fits safely in this window without either (a) porting unsafe GENESIS code, or (b) building a genuinely new capability (voice, vision, computer control, knowledge graph, skills/learning) that is itself a multi-day effort done properly through Avishkar's own contracts. Attempting more within 3 hours would mean cutting corners on exactly the things this repo's own established discipline (and your own directive's Part T/S) says not to cut.

## 22. MUST / SHOULD / OPTIONAL / FUTURE

**MUST** (this mission, if approved): `PersonalModel`, `ProactiveEngine`, their tests/docs.

**SHOULD** (a natural, low-risk Mission Layla 2, not this session): extend `PersonalModel` with a `relationships` category *with* an explicit confirmation-gate pattern (informed by, not copied from, `digital_founder_genome.py`'s sensitive-layer design) — deliberately excluded from Mission 1 given the time budget and the privacy stakes of getting it right the first time.

**OPTIONAL** (real value, real effort, needs its own dedicated planning pass): a genuine Knowledge Graph capability for Layla (Phase 6's vector search is not a graph; GENESIS's `knowledge_graph.py` proves the pattern is buildable in ~500 lines, but needs a from-scratch, privacy-gated Avishkar-native implementation); a real durable-scheduler enhancement inspired by GENESIS's dedup/retry-with-backoff design (Layla's `Scheduler` already has less than this — worth a dedicated look, but out of scope for a 3-hour window given it touches already-hardened Phase 17.4 concurrency code).

**FUTURE** (explicitly deferred, needs a full from-scratch security-first design, never a GENESIS port): Voice, Vision, Computer Control, IoT/Embodiment, Skills/Learning loop, external Channels/OAuth (though `core/auth/`'s *pattern* is worth a dedicated read when this is eventually built), Self-improvement/self-modification (if ever built at all — this one needs explicit, separate, very careful direction from you given what GENESIS's own version demonstrates about the failure mode).

## 23. Estimated Effort Per Component

| Component | Effort | Risk if rushed |
|---|---|---|
| `PersonalModel` | ~45-60 min incl. tests | Low — pure additive wrapper over existing, hardened `LaylaMemoryPolicy` |
| `ProactiveEngine` | ~45-60 min incl. tests | Low-Medium — must not bypass risk/approval; mitigated by routing every trigger through the existing `handle_event()` pipeline, never a shortcut |
| Wiring + example + docs | ~45-60 min | Low |
| Everything in SHOULD/OPTIONAL/FUTURE | Days each, not hours | High if compressed — explicitly not attempted this session |

## 24. Rollback Strategy

Every change in this mission is additive (new files + optional constructor parameters, matching the exact pattern every Phase 17 priority already established and proved safe 5 times over). Rollback is `git revert` of a single commit — no existing file's behavior changes when the new optional parameters are omitted, so even a partial rollback (reverting docs but keeping code, or vice versa) cannot break existing callers. No data migration, no schema change to existing types, nothing irreversible.

## 25. Acceptance Criteria

1. All 190 existing Layla tests still pass, unmodified.
2. New tests for `PersonalModel`/`ProactiveEngine` pass.
3. `ExecutiveRuntime` constructed with no new parameters behaves byte-for-byte identically to today (verified the same way every Phase 17 priority verified it — running the pre-existing suite unmodified).
4. The runnable example executes cleanly end-to-end.
5. No GENESIS file is copied, moved, or referenced by path from Avishkar-OS source.
6. No PII, credential, or GENESIS-specific data of any kind appears anywhere in the new code or docs.
7. Full regression, secret scan, and `git status` clean before final commit — matching this repo's own Phase 17 final-validation discipline.

## 26. Exact Files That Will Be Changed (if approved)

**New:**
- `layla/python/avishkar_layla/personal_model.py`
- `layla/python/avishkar_layla/proactive.py`
- `layla/python/tests/test_personal_model.py`
- `layla/python/tests/test_proactive.py`
- `layla/examples/personal_model_scenario.py`

**Modified:**
- `layla/python/avishkar_layla/runtime.py`
- `layla/python/avishkar_layla/__init__.py`
- `layla/CONTRACT.md`
- `layla/README.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `DECISIONS.md` (new ADR-0026)

## 27. Exact Files That Will NOT Be Changed

Everything else in Avishkar-OS — explicitly: `core/`, `router/`, every `factories/*`, every `agents/*`, `layla/python/avishkar_layla/{approval,audit,auth,capability_resolver,context,delegation,errors,execution,identity,intent,memory_policy,monitoring,notifications,planning,project,risk,scheduler,session,state_machine,synthesis,types}.py` (all untouched — new capabilities are additive alongside them, not modifications to them), and the entire GENESIS/`robot_ai` tree (read-only throughout this mission, zero writes performed — confirmed: no `Write`/`Edit` tool was invoked against any path under `Documents/robot_ai` at any point in this investigation).

---

# APPROVAL GATE

**NO IMPLEMENTATION HAS BEEN PERFORMED. WAITING FOR EXPLICIT APPROVAL.**

Say **"APPROVED — IMPLEMENT MISSION LAYLA 1"** to proceed with the plan exactly as scoped in §13–§21 above (PersonalModel + ProactiveEngine only). If you want a different scope approved (e.g., include the SHOULD/OPTIONAL items, or explicitly authorize a from-scratch computer-control design), say so explicitly — I will not expand scope on an ambiguous approval.
