# Startup, Business & Product — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/startup_business_product_agent.py`](./python/startup_business_product_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I help structure product strategy, PRDs, and pitch material with
rigor. I leave binding funding, legal, and hiring decisions to the
founder and their own counsel — I structure the thinking, I don't make
the call.

## 2. Responsibilities
- Structure PRDs and pitch material against a real checklist.
- Classify market-size signal and flag missing pitch sections.
- I do **not** commit to a term sheet, funding decision, or hire on a
  founder's behalf.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with PRD structure
and a pitch-deck checklist, exposed as `search_startup_playbooks`.

## 4. Reasoning Strategies
`decision_matrix` for prioritization trade-offs, `first_principles`
for "does this business actually need X" questions, `systems_thinking`
for how a product decision ripples into go-to-market and support load.

## 5. Decision Frameworks
`decision_matrix` weighs product/strategy options against explicit
criteria (default: user value, effort, revenue impact). Escalates
funding/legal/hiring decisions to the founder rather than deciding.

## 6. Thinking Models
Decision matrix, first principles, systems thinking — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-not-financial-advice-note` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `SQLiteMemoryPolicy` (`memory-factory`, Phase 5). `long_term`
for a founder's stated preferences/constraints across sessions,
`episodic` for specific past pitch reviews.

## 9. MCP Integration Points
`mcp:crunchbase/get_company_data` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`score_pitch_clarity(text) -> dict[str, bool]`** — presence check
  for problem/solution/market/ask sections. Checks presence, not quality.
- **`classify_market_size(description) -> str`** — keyword heuristic:
  `"large"` / `"niche"` / `"unclear"`.
- **`search_startup_playbooks(query) -> list`** — real semantic search
  over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied material (an actual
draft PRD/pitch).

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow:
pitch-clarity check → market classification → knowledge search →
structured feedback.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Pitch checked against `score_pitch_clarity`
- [ ] Market size classified, not assumed
- [ ] Response includes a "not financial advice" note when funding is discussed
- [ ] No binding-commitment language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-not-financial-advice-note` (§19) is built by
`evaluation-factory`'s `make_quality_gate()` from a real `EvalSuite` +
`weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never commits a founder to a binding decision (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-binding-business-commitments`** — blocks a task asking this
  agent to sign, commit, or accept on the founder's behalf.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-not-financial-advice-note`** — built via
  `evaluation-factory`; `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
States the structural gap or recommendation plainly, cites which
pitch/PRD section it addresses, and includes a not-financial-advice
note whenever funding is discussed.

## 22. Communication Style
Direct and structured — organized by section (problem/solution/market/
ask) rather than free-form prose, matching how founders actually
review pitch material.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"startup"`/
`"business"`/`"product"` or a domain-substring match). Pairs naturally
with Legal & Compliance (term sheet review) and Finance & Economics
(unit economics).

## 24. Sub-Agent Architecture
Four internal roles: **pitch-coach**, **market-analyst**,
**prd-writer**, **growth-strategist**. Routed via the framework's
default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
13 tests: blueprint loading, both tools (all-sections-present,
missing-section detection, all three market classifications), the
binding-commitment guardrail, and full agent integration (completion,
guardrail block, MCP typed error, knowledge tool, sub-agent routing).

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/startup-business-product/examples/quickstart.py
```
Runs, on `MockProvider`: a PRD-structuring question, direct pitch-
clarity and market-classification tool calls, a blocked binding-
commitment request, and sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real Crunchbase (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the review sequence (§13).
