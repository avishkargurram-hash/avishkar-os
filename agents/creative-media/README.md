# Creative & Media — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/creative_media_agent.py`](./python/creative_media_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I help draft, critique, and refine creative work — writing, scripts,
marketing copy. I never reproduce copyrighted material verbatim, and I
consistently encourage the creator's own original voice rather than
handing over a finished "final" piece as if it were theirs already.

## 2. Responsibilities
- Draft and critique creative writing, scripts, and marketing copy.
- Analyze word count and pacing to inform revision.
- Point to craft references (structure, editing principles).
- I do **not** reproduce copyrighted text verbatim.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` seeded with story-structure
basics and a copy-editing checklist, exposed as
`search_craft_references`.

## 4. Reasoning Strategies
`decision_matrix` for weighing stylistic choices against explicit
criteria, `systems_thinking` for how pacing/tone choices ripple across
a whole piece, `first_principles` for "does this scene actually need
to exist" questions.

## 5. Decision Frameworks
`decision_matrix` weighs creative choices against explicit criteria
(default: clarity, pacing, voice consistency). Escalates rather than
decides when a request risks copyright infringement.

## 6. Thinking Models
Decision matrix, systems thinking, first principles — see
`agent-factory`'s `thinking.py`; §4 for when each applies here.

## 7. Planning & Reflection
Standard plan → act → reflect loop, `max_iterations = 4`. The
`includes-originality-note` gate (§19) runs every iteration.

## 8. Memory Policies
Backed by `SQLiteMemoryPolicy` (`memory-factory`, Phase 5). `long_term`
for a creator's established voice/style preferences across sessions,
`episodic` for specific past drafts reviewed.

## 9. MCP Integration Points
`mcp:unsplash/search_stock_images` — declared, not yet resolvable;
raises `MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`count_words(text) -> int`** — a real, exact word count.
- **`analyze_pacing(text) -> str`** — sentence-length-variance
  heuristic: `"choppy"` / `"flowing"` / `"dense"` / `"unclear"` (fewer
  than two sentences). Not a certified stylometric measure.
- **`search_craft_references(query) -> list`** — real semantic search
  over the seeded `KnowledgeBase`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3) and task-supplied drafts.

## 12. Prompt Library
No versioned prompt library yet — real future work (§30).

## 13. Workflow Library
No standalone `workflows/` entry yet. Natural first workflow: pacing
analysis → craft-reference search → structured critique.

## 14. Template Library
No output-template library yet; output shape governed by §21.

## 15. Checklists
- [ ] Draft checked with `analyze_pacing` before critique
- [ ] Word count checked against any stated target
- [ ] Response frames output as a starting point, not a finished piece
- [ ] No verbatim reproduction of existing copyrighted work
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-originality-note` (§19) is built by `evaluation-factory`'s
`make_quality_gate()` from a real `EvalSuite` + `weighted_keyword_scorer`.

## 17. Security Policies
Never handles or echoes a credential (`no-secrets-in-task`, reused).
Never reproduces copyrighted material verbatim (§18).

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-verbatim-copyrighted-reproduction`** — blocks a task
  explicitly asking this agent to reproduce an existing copyrighted
  work's full text.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-originality-note`** — built via `evaluation-factory`;
  `threshold=0.0`, a soft signal today.

## 20. Error Recovery Strategies
Same shape as prior agents: failing gate retries within budget; a
blocked guardrail returns immediately with `status="blocked"`; router
failures propagate uncaught (tracked gap, §30).

## 21. Output Standards
Frames output explicitly as a draft/starting point, cites the pacing/
structure principle it applies, and never presents generated text as
already-owned finished work.

## 22. Communication Style
Encouraging but specific — critique names the exact sentence/section,
not vague praise or vague criticism.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"creative"`/
`"media"` or a domain-substring match). Pairs naturally with Startup,
Business & Product (marketing copy) and Legal & Compliance (rights
clearance questions).

## 24. Sub-Agent Architecture
Four internal roles: **story-editor**, **copywriter**,
**scriptwriter**, **brand-voice-consultant**. Routed via the
framework's default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper; `avishkar_agent` itself never changes.

## 26. Testing Strategy
14 tests: blueprint loading, both tools (all four pacing categories,
including a real bug caught by running the "dense" test — an initial
26-word-target fixture sentence was actually 19 words and classified
as "choppy" instead; fixed by rewriting the fixture, not the
threshold), the copyright guardrail, and full agent integration.

## 27. Versioning Strategy
Same semver discipline as prior agents: `blueprint.json.version`,
currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/creative-media/examples/quickstart.py
```
Runs, on `MockProvider`: a creative-writing question, direct word-
count and pacing tool calls, a blocked verbatim-reproduction request,
and sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` (§12, §14).
- A real Unsplash (or equivalent) MCP server resolving §9.
- A real `workflows/` entry externalizing the critique sequence (§13).
