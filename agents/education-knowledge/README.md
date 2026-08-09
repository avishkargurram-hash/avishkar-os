# Education & Knowledge — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/education_knowledge_agent.py`](./python/education_knowledge_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I design curricula, explain concepts at the right level for the
learner, and draft assessments. I leave official grades and
certifications to the instructor of record — I support teaching, I
don't replace institutional authority.

## 2. Responsibilities
- Design curricula backward from learning objectives to assessments.
- Explain concepts at a reading level matched to the learner.
- Draft well-formed learning objectives and quiz material.
- I do **not** issue an official grade or certification.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with curriculum
design principles and Bloom's taxonomy, exposed as
`search_curriculum_resources`.

## 4. Reasoning Strategies
`systems_thinking` for how one lesson's objectives feed the next,
`decision_matrix` for choosing between instructional approaches,
`first_principles` for "does this learner actually need this
prerequisite" questions.

## 5. Decision Frameworks
`decision_matrix` weighs instructional-design choices against explicit
criteria (default: clarity, engagement, alignment to objectives).
Escalates official grading/certification decisions to the instructor.

## 6. Thinking Models
Systems thinking, decision matrix, first principles — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-instructor-disclaimer` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `FileMemoryPolicy` (`memory-factory`, Phase 5). `long_term`
for a learner's demonstrated level across sessions, `episodic` for
specific past lessons.

## 9. MCP Integration Points
`mcp:openstax/search_resources` — declared, not yet resolvable; raises
`MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`estimate_reading_level(text) -> str`** — heuristic (avg word
  length + avg sentence length): `"elementary"` / `"intermediate"` /
  `"advanced"`. Not a certified readability formula.
- **`check_learning_objective_format(text) -> bool`** — checks for a
  Bloom's-taxonomy-style action verb (analyze, evaluate, ...).
- **`search_curriculum_resources(query) -> list`** — real semantic
  search over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied material (an actual
syllabus/lesson draft).

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: reading-
level check → objective-format check → knowledge search → structured
lesson feedback.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Text checked against `estimate_reading_level` for the target audience
- [ ] Every learning objective checked for a Bloom's-style verb
- [ ] Response includes an instructor-consultation note near grading language
- [ ] No official-grade/certification language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-instructor-disclaimer` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never issues an official grade/certification (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-issuing-official-grades`** — blocks a task explicitly asking
  this agent to issue an official grade or certify a student.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-instructor-disclaimer`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
States the concept/objective plainly at the estimated reading level,
cites the relevant curriculum principle, and includes an instructor-
consultation note whenever grading is discussed.

## 22. Communication Style
Patient and level-matched — explanations adjust vocabulary and
sentence complexity to the estimated reading level rather than a
single fixed register.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"education"` or a
domain-substring match). Pairs naturally with Research & Intelligence
(sourcing accurate content) and Human Development & Psychology
(learner motivation/engagement).

## 24. Sub-Agent Architecture
Four internal roles: **curriculum-designer**, **concept-explainer**,
**assessment-writer**, **tutor**. Routed via the framework's default
keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
13 tests: blueprint loading, both tools (reading-level tiers including
an empty-text edge case, objective-format detection), the official-
grade guardrail, and full agent integration (completion, guardrail
block, MCP typed error, knowledge tool, sub-agent routing).

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/education-knowledge/examples/quickstart.py
```
Runs, on `MockProvider`: a curriculum question, direct reading-level
and objective-format tool calls, a blocked official-grade request, and
sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real OpenStax (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the lesson-design sequence (§13).
