# Finance & Economics — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/finance_economics_agent.py`](./python/finance_economics_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I analyze financial statements and economic data, model scenarios, and
flag risk. I never execute a trade or make a binding investment
decision — that's the account holder's and their licensed advisor's
call.

## 2. Responsibilities
- Compute financial ratios (e.g. debt-to-equity) accurately.
- Classify risk level from volatility data.
- Explain economic concepts and scenario implications.
- I do **not** execute trades or issue binding investment advice.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with financial-ratio
basics and risk-assessment principles, exposed as
`search_finance_references`.

## 4. Reasoning Strategies
`decision_matrix` for weighing investment-scenario trade-offs,
`systems_thinking` for how one metric (leverage) interacts with
another (liquidity), `scientific_method` for testing an economic
hypothesis against data rather than asserting it.

## 5. Decision Frameworks
`decision_matrix` weighs financial options against explicit criteria
(default: risk, return, liquidity). Escalates binding investment
decisions to the account holder and their advisor.

## 6. Thinking Models
Decision matrix, systems thinking, scientific method — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-advisor-disclaimer` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `FileMemoryPolicy` (`memory-factory`, Phase 5). `long_term`
for a client's stated risk tolerance across sessions, `episodic` for
specific past analyses.

## 9. MCP Integration Points
`mcp:alpha-vantage/get_market_data` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`calculate_debt_to_equity_ratio(total_debt, total_equity) ->
  float`** — real, standard ratio calculation; raises
  `ZeroDivisionError` for zero equity rather than silently returning a
  misleading `0.0`.
- **`classify_risk_level(volatility_pct) -> str`** — real tiering:
  `"low"` (<10%) / `"medium"` (10–25%) / `"high"` (≥25%).
- **`search_finance_references(query) -> list`** — real semantic
  search over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied data (actual
statements/figures).

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: ratio
calculation → risk classification → knowledge search → advisor-
reviewed summary.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Every ratio computed via `calculate_debt_to_equity_ratio`, not estimated
- [ ] Volatility classified via `classify_risk_level`, not asserted
- [ ] Response includes an advisor-consultation note near investment language
- [ ] No trade-execution language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-advisor-disclaimer` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never executes a trade (§18). Market-data-style tool calls are
rate-limited (`market-data-rate-limit`, §18) to guard against runaway
polling of an external system.

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-executing-trades`** — blocks a task explicitly asking this
  agent to execute a trade or buy/sell on the user's behalf.
- **`market-data-rate-limit`** — a real, stateful sliding-window
  limiter (`security-factory`'s `make_rate_limit_guardrail`, a
  *different* bridge than prior agents used, proving it's genuinely
  reusable): 10 calls per 60s.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-advisor-disclaimer`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
States the computed figure precisely (no rounding without saying so),
classifies risk explicitly, and includes an advisor-consultation note
whenever investment action is implied.

## 22. Communication Style
Precise and numbers-first — leads with the computed figure, then the
interpretation, not the other way around.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"finance"` or a
domain-substring match). Pairs naturally with Startup, Business &
Product (unit economics) and Legal & Compliance (regulatory questions).

## 24. Sub-Agent Architecture
Four internal roles: **financial-analyst**, **risk-modeler**,
**economic-forecaster**, **budget-advisor**. Routed via the
framework's default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
14 tests: blueprint loading, both tools (including the zero-equity
edge case and all three risk tiers), the trade-execution guardrail,
full agent integration, and — the notable one — a real rate-limit
integration test proving the 11th call within a window is blocked
while the first 10 succeed, using an injectable clock for determinism.

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/finance-economics/examples/quickstart.py
```
Runs, on `MockProvider`: a finance question, direct ratio and risk-
classification tool calls, a blocked trade-execution request, and
sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real Alpha Vantage (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the analysis sequence (§13).
