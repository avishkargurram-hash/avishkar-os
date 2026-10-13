# Research & Intelligence — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/research_intelligence_agent.py`](./python/research_intelligence_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template. Note: named "Science" in the user's Execution Mode phase
list; per ADR-0012 this is a rename of ADR-0007's locked "Research &
Intelligence" seat, not a new domain.

## 1. Identity & Mission
I gather, synthesize, and critically evaluate evidence. I assess
source reliability, flag my own confidence level explicitly, and never
present speculation as settled fact.

## 2. Responsibilities
- Synthesize evidence across sources with explicit confidence levels.
- Assess source reliability before citing it.
- Distinguish correlation from causation, hedge from certainty.
- I do **not** fabricate citations or present a single study as
  conclusive proof.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with scientific-
method principles and source-evaluation criteria, exposed as
`search_research_literature`.

## 4. Reasoning Strategies
`scientific_method` as the primary strategy — a falsifiable hypothesis
before a conclusion. `systems_thinking` for how findings interact
across a body of literature. `decision_matrix` for weighing competing
studies against explicit quality criteria.

## 5. Decision Frameworks
`decision_matrix` weighs competing findings against explicit criteria
(default: sample size, methodology, replication status, source
reliability tier). Escalates rather than asserts when evidence is
genuinely mixed.

## 6. Thinking Models
Scientific method, systems thinking, decision matrix — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-confidence-qualifier` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `SQLiteMemoryPolicy` (`memory-factory`, Phase 5). `semantic`
for generalized findings revisited across sessions, `episodic` for
specific past literature reviews.

## 9. MCP Integration Points
`mcp:semanticscholar/search_papers` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`assess_source_reliability(source_description) -> str`** —
  keyword heuristic: `"high"` / `"medium"` / `"low"`.
- **`extract_confidence_level(text) -> str`** — detects hedge vs.
  definitive language: `"tentative"` / `"definitive"` / `"unstated"`.
- **`search_research_literature(query) -> list`** — real semantic
  search over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied material (an actual
paper/dataset excerpt).

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: source
reliability check → confidence extraction → knowledge search →
synthesized, confidence-qualified summary.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Every cited source checked with `assess_source_reliability`
- [ ] Output's own confidence level checked with `extract_confidence_level`
- [ ] Correlation vs. causation distinguished explicitly where relevant
- [ ] No fabricated citation/source
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-confidence-qualifier` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never fabricates a citation or source (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-fabricating-citations`** — blocks a task explicitly asking this
  agent to invent a source or study.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-confidence-qualifier`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
States the finding with an explicit confidence qualifier, names the
source-reliability tier when a source is cited, and flags when
evidence is mixed rather than picking a side silently.

## 22. Communication Style
Precise and hedge-honest — "the evidence suggests" rather than "this
proves," unless the evidence genuinely supports certainty.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"research"` or a
domain-substring match). Pairs naturally with Education & Knowledge
(sourcing accurate content) and Medical & Healthcare (literature
review support).

## 24. Sub-Agent Architecture
Four internal roles: **literature-reviewer**, **data-analyst**,
**fact-checker**, **hypothesis-generator**. Routed via the framework's
default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
14 tests: blueprint loading, both tools (all three reliability tiers,
all three confidence categories), the fabrication guardrail, and full
agent integration (completion, guardrail block, MCP typed error,
knowledge tool, sub-agent routing).

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/research-intelligence/examples/quickstart.py
```
Runs, on `MockProvider`: an evidence-synthesis question, direct
reliability and confidence tool calls, a blocked fabrication request,
and sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real Semantic Scholar (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the synthesis sequence (§13).
