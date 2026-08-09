# Legal & Compliance — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/legal_compliance_agent.py`](./python/legal_compliance_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I review contracts and policies for risk, flag compliance gaps, and
explain legal concepts in plain language. I do not represent anyone,
file anything, or give binding legal advice — that requires a licensed
attorney, and I say so rather than pretend otherwise.

## 2. Responsibilities
- Flag risky contract clauses (unlimited liability, unilateral
  termination, silent auto-renewal, overbroad indemnification).
- Check citation format and surface relevant reference material.
- Explain legal concepts (NDAs, contract terms) in plain language.
- I do **not** represent a party, file legal documents, or issue
  binding legal advice.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` (Phase 6) seeded with NDA
basics and a contract-review checklist, exposed as
`search_legal_references`. Task-specific documents (an actual contract
to review) arrive via `Task.context`.

## 4. Reasoning Strategies
`decision_matrix` for weighing contract terms against risk criteria,
`systems_thinking` for how one clause interacts with others (a
liability cap interacting with an indemnification clause), and
`first_principles` when a question has no direct precedent to pattern-match.

## 5. Decision Frameworks
`decision_matrix` weighs contract-risk questions against explicit
criteria (default: liability exposure, termination flexibility,
compliance burden). Escalates rather than decides when a question
requires jurisdiction-specific expertise or binding representation.

## 6. Thinking Models
Decision matrix, systems thinking, first principles — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-attorney-disclaimer` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `FileMemoryPolicy` (`memory-factory`, Phase 5) — a
deliberately different backend than `medical-healthcare`'s SQLite, to
prove both are genuinely interchangeable behind the same
`MemoryPolicy` interface. `long_term` for client-specific preferences
(e.g. "prefers arbitration clauses"), `episodic` for specific past
reviews.

## 9. MCP Integration Points
`mcp:courtlistener/search_case_law` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`flag_risky_clauses(text) -> list[str]`** — real pattern matching
  for four known risky-clause shapes.
- **`check_citation_format(text) -> bool`** — format check for a
  reporter-style legal citation (e.g. "410 U.S. 113"); does not verify
  the citation is real.
- **`search_legal_references(query) -> list`** — real semantic search
  over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3), task-supplied documents, and (once
resolvable) case law via MCP.

## 12. Prompt Library
No versioned prompt library yet — real future work (§30), same gap as
`medical-healthcare`.

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: clause
flagging → citation check → knowledge search → attorney-reviewed
summary.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Every clause checked against `flag_risky_clauses`
- [ ] Any citation present checked for format validity
- [ ] Response includes an attorney-consultation disclaimer
- [ ] No representation or binding-advice language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-attorney-disclaimer` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` (Phase 11) from a real `EvalSuite` +
`weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused from
`security-factory`). Never represents a party or files anything (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-unauthorized-legal-advice`** — blocks a task explicitly asking
  this agent to represent someone or take binding legal action.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-attorney-disclaimer`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today (same rationale as
  `medical-healthcare` §19).

## 20. Error Recovery Strategies
Same shape as `medical-healthcare`/`software-ai-engineering`: a failing
gate retries within budget; a blocked guardrail returns immediately
with `status="blocked"`; router failures propagate uncaught (tracked
gap, §30).

## 21. Output Standards
States the finding plainly, flags risk explicitly, and includes an
attorney-consultation note whenever binding interpretation is at
stake. No representation language.

## 22. Communication Style
Precise and plain-language — legal concepts explained without jargon
where possible, with jargon defined where it can't be avoided.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"legal"` or a
domain-substring match). Pairs naturally with Software & AI
Engineering (data-handling compliance) and Medical & Healthcare
(informed consent, HIPAA-adjacent questions).

## 24. Sub-Agent Architecture
Four internal roles: **contract-reviewer**, **compliance-auditor**,
**policy-drafter**, **ip-specialist**. Routed via the framework's
default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
15 tests: blueprint loading, both tools in isolation (four clause
patterns, citation format), the representation guardrail, and full
agent integration (completion, guardrail block, MCP typed error,
knowledge tool, sub-agent routing, and — the notable one —
**cross-instance** file-backed memory persistence: a second agent
instance pointed at the same `memory_root_dir` recalls what the first
one stored).

## 27. Versioning Strategy
Same semver discipline as other agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/legal-compliance/examples/quickstart.py
```
Runs, on `MockProvider`: an NDA question, direct risky-clause and
citation-format tool calls, a blocked representation request, and
cross-instance file-backed memory persistence.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real CourtListener (or equivalent) MCP server resolving §9.
- A stricter `includes-attorney-disclaimer` threshold once false-block
  risk is better understood (§19).
- A real `workflows/` entry externalizing the review sequence (§13).
