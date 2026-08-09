# Orchestrator — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md)'s
real `Orchestrator` class (Phase 3) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package:
[`python/orchestrator_agent.py`](./python/orchestrator_agent.py) — no
`blueprint.json` (§1 explains why). Documented to
[STANDARDS.md](../../STANDARDS.md) §2.3's 30-section template. Called
"Executive Orchestrator" in the Execution Mode phase list; per
ADR-0012 this is the same locked ADR-0007 seat, not a new one.

## 1. Identity & Mission
I am the coordination layer: I know which of the 10 domain agents
should handle a task, or which combination should weigh in together. I
have no domain expertise of my own — I never answer a question myself,
I route it. This is why I have no `blueprint.json`: `AgentBlueprint`
describes one reasoning agent's mission/tools/guardrails, and I'm not
a reasoning agent — I'm the composition of ten. `avishkar_agent.Orchestrator`
(built and locked in Phase 3) already *is* my implementation; this
package's only job is building all 10 real domain agents and handing
them to it.

## 2. Responsibilities
- Route a task to the one domain agent that should handle it
  (`route()`).
- Dispatch the same task to several named agents for a combined view
  (`delegate_team()`).
- Broadcast the same task to several agents independently for
  comparison (`broadcast()`).
- Resolve a conflict among multiple candidate results
  (`resolve_conflict()`).
- I do **not** perform domain reasoning myself — that's each of the 10
  agents' job.

## 3. Domain Knowledge Architecture
None of my own — I hold no `KnowledgeBase`. Each domain agent owns its
own (§3 of each agent's own README); I only know their names and
domains well enough to route.

## 4. Reasoning Strategies
None of my own. `avishkar_agent.Orchestrator._match_one` uses a fixed,
deterministic strategy: exact `task_type == agent.name` match first,
then a domain-substring fallback, raising `NoMatchingAgentError` rather
than guessing when more than one agent could plausibly match (Phase 3,
CONTRACT.md SS7).

## 5. Decision Frameworks
`resolve_conflict(results, strategy)` supports named, pluggable
strategies: `"first_completed"` (first result with `status ==
"completed"`) and `"prefer_agent:<name>"` (a specific agent's result
wins regardless of order). Both are real, tested implementations from
Phase 3 — this package doesn't add new ones, it uses what exists.

## 6. Thinking Models
None — I don't reason about task content, only about which agent(s)
should.

## 7. Planning & Reflection
None of my own. Each dispatched agent runs its own full plan → act →
reflect loop (see that agent's own README §7); I only decide *who*
runs it.

## 8. Memory Policies
No memory of my own in this v1 (`avishkar_agent.Orchestrator`'s
optional `shared_memory` parameter is not wired here — see Future
Roadmap). Each domain agent has its own real memory backend, documented
in that agent's own README §8.

## 9. MCP Integration Points
None of my own. Each domain agent declares its own `MCPToolRef`s
(§9 of each agent's own README).

## 10. Tool Registry
None of my own. `build_all_domain_agents(router, model_override=None)
-> Dict[str, ChiefDomainAgent]` is the one function this package adds:
it builds all 10 real domain agents (each with its own real tools) and
returns them keyed by name. `build_executive_orchestrator(router,
model_override=None) -> Orchestrator` composes them under a real
`avishkar_agent.Orchestrator`.

## 11. Knowledge Sources
None of my own — see §3.

## 12. Prompt Library
None of my own — I never call a model.

## 13. Workflow Library
This package *is* the natural first cross-agent workflow: task in,
routed (or team-dispatched, or broadcast) to the right domain
agent(s), result out. A real `workflow-factory` `WorkflowSpec` wrapping
this is real future work (§30), not built speculatively here.

## 14. Template Library
None of my own.

## 15. Checklists
- [ ] `task.task_type` set to an exact agent name (or a domain
      substring only one agent matches) before calling `route()`
- [ ] `delegate_team()`/`broadcast()` used, not `route()`, when more
      than one agent's perspective is genuinely needed
- [ ] A `resolve_conflict()` strategy chosen deliberately, not defaulted

## 16. Evaluation Framework
None of my own — each domain agent's own quality gates (§16/§19 of
its README) already run inside its own `handle()` call before a result
ever reaches me.

## 17. Security Policies
None of my own beyond what each domain agent already enforces (its
own guardrails run before I ever see a completed result). I don't
introduce a new attack surface — I only call already-guarded agents.

## 18. Guardrails
None of my own. See §17.

## 19. Quality Gates
None of my own. See §16.

## 20. Error Recovery Strategies
`_match_one` raises `NoMatchingAgentError` rather than guessing when
`task_type` is missing or ambiguous (Phase 3, unchanged here).
`resolve_conflict` raises `NoMatchingAgentError`/`ValueError` for an
unresolvable conflict/unknown strategy rather than silently picking
one. Neither is new work — this package just exercises what Phase 3
already built correctly.

## 21. Output Standards
Whatever the dispatched agent's own Output Standards section (§21)
says — I pass its `AgentResult` through unchanged.

## 22. Communication Style
None of my own — I don't generate text.

## 23. Collaboration Protocols
I *am* the collaboration protocol other agents plug into. Every one of
the 10 domain agents' own §23 describes how it's reachable through me.

## 24. Sub-Agent Architecture
Not applicable in the usual sense — my "sub-agents" are the 10 full
Chief Domain Agents themselves, not internal expert roles absorbed
into one domain (contrast every other agent's §24). This is the one
structural way I differ from the rest of the roster, and it's
intentional: ADR-0007 named exactly this shape ("one Orchestrator that
decides which domain agents collaborate").

## 25. Extensibility Model
A new domain agent (a 12th roster seat, requiring its own ADR per
ADR-0007) is added to `build_all_domain_agents()`'s tuple; nothing
about `avishkar_agent.Orchestrator` itself changes.

## 26. Testing Strategy
7 tests: `build_all_domain_agents` builds exactly 10 agents by exact
name, and — the strongest test in this package — **every one of the
10 actually completes a real task** (`subTest` per agent, not just
"constructs without error"). `build_executive_orchestrator`'s
`route()`, `delegate_team()`, `broadcast()`, and `resolve_conflict()`
are each exercised against real dispatched results.

## 27. Versioning Strategy
No `blueprint.json` to version (§1). This package's own version is
implicit in this repository's commit history; a breaking change to
`build_all_domain_agents`'s signature would be called out explicitly
in a commit message and `CHANGELOG.md`, same discipline as every other
change in this repository.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/orchestrator/examples/quickstart.py
```
Runs, on `MockProvider`: builds all 10 domain agents, lists them,
routes a task by exact name, delegates one task to two named agents,
broadcasts a task to two more, and resolves a conflict among the
broadcast results — the entire platform, composed and running.

## 30. Future Roadmap
- Wire `avishkar_agent.Orchestrator`'s optional `shared_memory`
  parameter to a real `memory-factory` backend, giving cross-agent
  context a durable home (§8).
- A real `workflow-factory` `WorkflowSpec` wrapping common multi-agent
  patterns (§13) as a reusable, named workflow rather than inline
  Python calls.
- Concurrent (not sequential) `delegate_team()`/`broadcast()`
  dispatch, once `avishkar_agent.Orchestrator` itself supports it
  (tracked in `agent-factory`'s own Future Roadmap, not duplicated
  here).
