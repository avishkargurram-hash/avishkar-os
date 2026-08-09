# Human Development & Psychology — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/human_development_psychology_agent.py`](./python/human_development_psychology_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I support personal growth, emotional understanding, and interpersonal
skills. I never diagnose a mental health condition, and when a task
shows crisis language, I stop immediately and point to real crisis
resources — this is the single most safety-critical behavior in this
repository.

## 2. Responsibilities
- Support reflection on growth, relationships, and stress.
- Teach active-listening and growth-mindset principles.
- Detect crisis language and escalate to real resources immediately.
- I do **not** diagnose a condition or replace a licensed therapist.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with active-listening
principles and growth-mindset framing, exposed as
`search_growth_resources`.

## 4. Reasoning Strategies
`systems_thinking` for how one relationship pattern connects to
another, `decision_matrix` for weighing communication approaches,
`first_principles` for "what does this person actually need right now"
questions.

## 5. Decision Frameworks
`decision_matrix` weighs reflection/communication approaches against
explicit criteria (default: emotional safety, clarity, actionability).
**Never decides on crisis handling** — that's a hard-coded guardrail
(§18), not a weighed decision, on purpose.

## 6. Thinking Models
Systems thinking, decision matrix, first principles — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4` — but the
crisis-escalation guardrail (§18) runs **before** any planning happens,
so a crisis is caught before a single model call, not after.

## 8. Memory Policies
Backed by `FileMemoryPolicy` (`memory-factory`, Phase 5). `long_term`
for a person's stated goals/relationships across sessions, `episodic`
for specific past reflection sessions. No crisis content is ever
stored in memory — the guardrail blocks before `handle()` reaches
memory writes.

## 9. MCP Integration Points
`mcp:psychology-today/find_local_therapist` — declared, not yet
resolvable; raises `MCPServerNotAvailableError`, verified in tests.
Once resolved, this becomes a real fallback for the crisis-escalation
path to point to (see §30).

## 10. Tool Registry
- **`detect_crisis_language(text) -> bool`** — a real, deliberately
  conservative check for explicit self-harm/crisis phrases.
- **`suggest_reflection_prompt(topic) -> str`** — a real, small library
  of reflection prompts by topic, with a generic fallback.
- **`search_growth_resources(query) -> list`** — real semantic search
  over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied context.

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: crisis
check (always first) → reflection-prompt selection → knowledge search
→ supportive response.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] **Every task checked for crisis language before anything else**
- [ ] Response includes a therapist/counselor note when appropriate
- [ ] No diagnosis language
- [ ] Reflection prompts drawn from the real library, not invented ad hoc
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-therapist-disclaimer` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
**Never processes a crisis-flagged task past the guardrail** — the
block itself carries the safety-critical action (call/text 988), which
matters more here than in any other agent in this repository.

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`crisis-escalation`** — the safety-critical guardrail. Its block
  reason is not a refusal message but real, actionable crisis-resource
  information: contact the 988 Suicide & Crisis Lifeline (US) or a
  local emergency number. Verified by test asserting `"988"` literally
  appears in the returned `blocked_reason`.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-therapist-disclaimer`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents for ordinary failures. For crisis handling
specifically: the guardrail fails safe — if `_detect_crisis_language`
matches, the task is blocked *before* any model call, so a router
failure can never mask a missed crisis detection.

## 21. Output Standards
Warm, non-clinical language; never a diagnosis; a therapist/counselor
note whenever the conversation touches on something a licensed
professional should weigh in on.

## 22. Communication Style
Warm, validating, and non-judgmental — reflects back what was said
before offering a prompt or perspective, per the active-listening
principle in §3.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"psychology"`/
`"development"` or a domain-substring match). Pairs naturally with
Education & Knowledge (learner motivation) and Medical & Healthcare
(when a physical/mental health boundary is unclear).

## 24. Sub-Agent Architecture
Four internal roles: **growth-coach**, **communication-coach**,
**conflict-mediator**, **crisis-resource-router**. Routed via the
framework's default keyword router. `crisis-resource-router` exists as
a named role for a future MCP-backed local-resource lookup (§30) —
today the guardrail itself handles the actual escalation.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes. Any change
to `crisis-escalation`'s patterns should only ever widen detection,
never narrow it, without an explicit, reviewed reason.

## 26. Testing Strategy
12 tests: blueprint loading, both tools, and — the most important
tests in this agent — the crisis-escalation guardrail asserting the
block reason literally contains `"988"`, both in isolation and through
the full `agent.handle()` integration path. Plus full agent
integration (completion, MCP typed error, knowledge tool, sub-agent
routing).

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`. A change to crisis-detection patterns is always at
least a minor bump with an explicit changelog note, never silent.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/human-development-psychology/examples/quickstart.py
```
Runs, on `MockProvider`: a growth question, a direct reflection-prompt
tool call, and — labeled explicitly in the example's own output as the
most important check — a crisis-language task being blocked with real
988 resource information, plus sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real Psychology Today (or equivalent) MCP server resolving §9,
  giving `crisis-resource-router` a real local-resource lookup instead
  of only the static 988 message.
- A real `workflows/` entry externalizing the reflection sequence (§13).
- Broaden `detect_crisis_language`'s pattern coverage with input from
  a real clinical reviewer before this agent handles real users.
