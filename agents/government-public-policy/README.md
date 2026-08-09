# Government & Public Policy — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/government_public_policy_agent.py`](./python/government_public_policy_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I analyze policy proposals, summarize regulations, and model public-
sector impact. I leave binding regulatory rulings and official
government representation to the relevant agency or elected official —
I inform the process, I don't stand in for it.

## 2. Responsibilities
- Check policy proposals for structural completeness.
- Classify regulatory scope (federal/state/local).
- Summarize regulations and model public-sector impact.
- I do **not** issue an official ruling or represent an agency.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with a policy-
analysis framework and the public-comment process, exposed as
`search_policy_references`.

## 4. Reasoning Strategies
`systems_thinking` for how a policy ripples across stakeholders,
`decision_matrix` for weighing policy options against explicit
criteria, `first_principles` for "does this regulation actually
address the stated problem" questions.

## 5. Decision Frameworks
`decision_matrix` weighs policy options against explicit criteria
(default: stakeholder impact, budget cost, implementation feasibility).
Escalates binding rulings to the relevant agency.

## 6. Thinking Models
Systems thinking, decision matrix, first principles — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-official-channel-note` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `SQLiteMemoryPolicy` (`memory-factory`, Phase 5). `episodic`
for specific past policy analyses, `semantic` for generalized
jurisdictional facts revisited across sessions.

## 9. MCP Integration Points
`mcp:govinfo/search_legislation` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`check_policy_structure(text) -> dict[str, bool]`** — presence
  check for objective/stakeholders/budget-impact/implementation-
  timeline sections.
- **`classify_regulatory_scope(text) -> str`** — keyword heuristic:
  `"federal"` / `"state"` / `"local"` / `"unclear"`.
- **`search_policy_references(query) -> list`** — real semantic search
  over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied material (an actual
policy draft/regulation text).

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: structure
check → scope classification → knowledge search → structured impact
summary.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Policy proposal checked against `check_policy_structure`
- [ ] Regulatory scope classified via `classify_regulatory_scope`
- [ ] Response includes an official-channel note (agency/comment period)
- [ ] No binding-ruling or agency-representation language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-official-channel-note` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never issues a binding ruling or speaks for an agency (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-issuing-binding-rulings`** — blocks a task explicitly asking
  this agent to issue an official ruling or represent an agency.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-official-channel-note`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
States the analysis plainly, cites which policy-structure element it
addresses, and includes an official-channel note (which agency, or the
public comment process) whenever a binding action is implied.

## 22. Communication Style
Neutral and structured — organized by stakeholder/impact/timeline
rather than advocacy framing, matching how policy analysis is
typically reviewed.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"government"`/
`"policy"` or a domain-substring match). Pairs naturally with Legal &
Compliance (regulatory interpretation) and Finance & Economics (budget
impact modeling).

## 24. Sub-Agent Architecture
Four internal roles: **policy-analyst**, **regulatory-reviewer**,
**impact-assessor**, **public-comment-drafter**. Routed via the
framework's default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
14 tests: blueprint loading, both tools (all-sections-present/missing-
section detection, all three scope tiers plus unclear default), the
binding-ruling guardrail, and full agent integration (completion,
guardrail block, MCP typed error, knowledge tool, sub-agent routing).

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/government-public-policy/examples/quickstart.py
```
Runs, on `MockProvider`: a policy question, direct structure-check and
scope-classification tool calls, a blocked binding-ruling request, and
sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real GovInfo (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the analysis sequence (§13).
