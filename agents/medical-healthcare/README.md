# Medical & Healthcare — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010. Package: `blueprint.json` +
[`python/medical_healthcare_agent.py`](./python/medical_healthcare_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission
I support clinical information needs — summarizing evidence, flagging
drug interactions, and triaging urgency — while never replacing a
licensed clinician's judgment. When a task asks me to prescribe,
diagnose definitively, or bypass a doctor, I say so and stop, not
guess.

## 2. Responsibilities
- Summarize clinical guidelines relevant to a question.
- Flag known drug-drug interactions and urgency level from described
  symptoms.
- Educate patients on their own conditions/treatment in plain language.
- I do **not** issue a definitive diagnosis, prescribe medication, or
  substitute for an in-person clinical evaluation.

## 3. Domain Knowledge Architecture
A real `knowledge-factory` `KnowledgeBase` (Phase 6) holds two seed
clinical guideline documents (hypertension, diabetes), exposed as the
`search_clinical_guidelines` tool. Layer 2 (general medical literature)
is caller-supplied via `Task.context` today; a real `pubmed` MCP server
(declared, §9) will widen this without a blueprint change.

## 4. Reasoning Strategies
`scientific_method` for symptom-to-hypothesis reasoning (falsifiable,
not a guess), `decision_matrix` for weighing treatment options against
explicit criteria, `systems_thinking` for interactions between
conditions/medications rather than treating each in isolation.

## 5. Decision Frameworks
`decision_matrix` weighs treatment-option questions against efficacy,
safety, and patient-specific contraindications by default. Escalates
(refuses to decide) when the question requires an in-person exam,
lab result, or licensed prescribing authority I don't have.

## 6. Thinking Models
Scientific method, decision matrix, systems thinking — see
`agent-factory`'s `thinking.py` for the shared implementations; §4
above for when each applies here specifically.

## 7. Planning & Reflection
Standard plan → act → reflect loop (`ChiefDomainAgent.handle`, up to
`max_iterations = 4`). The `includes-clinician-disclaimer` quality gate
(§19) is evaluated every iteration; a fully exhausted budget without a
passing gate still returns the best candidate as `"failed"`, not
silently `"completed"`.

## 8. Memory Policies
Backed by `SQLiteMemoryPolicy` (`memory-factory`, Phase 5) — real,
persistent memory, not process-local. `episodic` for specific
encounters ("reported mild headache on visit 1"), `semantic` for
generalized patient facts ("known NSAID sensitivity"), `short_term`
for the current conversation's working context. No real PHI is stored
in this repository's tests/examples — `memory_db_path` defaults to
`:memory:` for exactly that reason.

## 9. MCP Integration Points
`mcp:pubmed/search_literature` — declared via `MCPToolRef`, not yet
resolvable (no real PubMed MCP server exists). Calling it raises
`MCPServerNotAvailableError`, verified in tests.

## 10. Tool Registry
- **`check_drug_interactions(drug_a, drug_b) -> Optional[str]`** — a
  real, small lookup table of well-known dangerous interactions
  (warfarin+aspirin, SSRI+MAOI, etc.). Not exhaustive.
- **`flag_urgency(symptoms: str) -> str`** — keyword-based triage
  heuristic: `"emergency"` / `"urgent"` / `"routine"`.
- **`search_clinical_guidelines(query) -> list`** — real semantic
  search over the seeded `KnowledgeBase` (§3), wrapped via
  `knowledge-factory`'s `as_tool()`.

## 11. Knowledge Sources
The seeded `KnowledgeBase` (§3), general medical literature via
`Task.context` today, and (once resolvable) PubMed via MCP.

## 12. Prompt Library
No versioned prompt library yet (`prompt-factory` exists as of Phase 8
but this agent hasn't been migrated to it — real future work, tracked
in §30). Prompt construction is `ChiefDomainAgent._act`'s standard
mission+task+approach framing.

## 13. Workflow Library
No standalone `workflows/` entry yet. The natural first workflow:
triage → guideline search → clinician-reviewed answer — composable via
`workflow-factory` (Phase 7) once a real deployment needs it externalized.

## 14. Template Library
No output-template library yet (`template-factory`, Phase 9, not yet
wired to this agent). Output shape is governed directly by §21.

## 15. Checklists
- [ ] Urgency flagged before any substantive answer to a symptom question
- [ ] Any drug pair mentioned is checked via `check_drug_interactions`
- [ ] Response includes a clinician-consultation disclaimer
- [ ] No prescribing or definitive diagnosis language
- [ ] No secret/credential present in the task (guardrail-enforced)

## 16. Evaluation Framework
`includes-clinician-disclaimer` (§19) is a real `QualityGate` built by
`evaluation-factory`'s `make_quality_gate()` (Phase 11) from an
`EvalSuite` + `weighted_keyword_scorer` — not hand-written, unlike
`software-ai-engineering`'s Phase-3-era gates.

## 17. Security Policies
Never asked to handle or echo a credential — `make_secret_scanning_guardrail()`
(`security-factory`, Phase 12, reused not reimplemented) blocks that
before any model call. Never autonomously prescribes (§18). No real
PHI is committed anywhere in this repository.

## 18. Guardrails
- **`no-secrets-in-task`** — reused verbatim from `security-factory`.
- **`no-autonomous-prescribing`** — blocks a task explicitly asking
  this agent to prescribe/dose/self-medicate/skip a doctor.

## 19. Quality Gates
- **`minimum-substance`** — output ≥ 10 non-whitespace characters.
- **`includes-clinician-disclaimer`** — built via `evaluation-factory`
  (§16); `threshold=0.0` today (a soft signal, not a hard block) —
  see Limitations for why a stricter threshold isn't safely enforced
  yet.

## 20. Error Recovery Strategies
A failing quality gate triggers another iteration (§7). A blocked
guardrail returns immediately with `status="blocked"` and a
`blocked_reason`. Router-level failures propagate uncaught, same
documented gap as `software-ai-engineering` §20.

## 21. Output Standards
States the information plainly, flags urgency when symptoms are
involved, and includes a clinician-consultation note whenever
treatment or diagnosis is discussed. No prescribing language.

## 22. Communication Style
Calm, plain-language, and explicit about uncertainty — "this is
consistent with X, but a clinician should confirm" rather than false
certainty.

## 23. Collaboration Protocols
Reachable through `Orchestrator.route()` (task_type `"medical"` or a
domain-substring match on "Medical & Healthcare"). Participates in
`delegate_team()`/`broadcast()` alongside other Chief Domain Agents —
e.g. paired with Legal & Compliance for questions with a regulatory
angle (informed consent, HIPAA-adjacent).

## 24. Sub-Agent Architecture
Four internal roles: **diagnostician-support** (differential-style
reasoning support, not a diagnosis), **medication-reviewer**
(interaction checks), **triage-specialist** (urgency flagging),
**patient-educator** (plain-language explanation). Routed via the
framework's default keyword router.

## 25. Extensibility Model
New tools/guardrails/quality gates register in the matching
`_build_*()` helper. None of this touches `avishkar_agent` itself.

## 26. Testing Strategy
16 tests: blueprint loading, both tools in isolation (interaction
lookup order/case-insensitivity, urgency keyword tiers), the
prescribing guardrail, and full agent integration (normal completion,
guardrail block, the declared MCP tool's typed error, the knowledge
tool, sub-agent routing, and memory persistence within the agent's
lifetime).

## 27. Versioning Strategy
Same semver discipline as `software-ai-engineering` §27:
`blueprint.json.version`, currently `0.1.0`.

## 28. Documentation
This README is the primary source.

## 29. Examples
```bash
python agents/medical-healthcare/examples/quickstart.py
```
Runs, on `MockProvider`: a clinical question with a real knowledge
search, a direct drug-interaction check, urgency triage on two inputs,
a blocked prescribing request, and sub-agent routing.

## 30. Future Roadmap
- Migrate to `prompt-factory`/`template-factory` for versioned prompts
  and output templates (§12, §14).
- A real PubMed (or equivalent) MCP server resolving §9 without any
  blueprint change.
- A stricter `includes-clinician-disclaimer` threshold once false-block
  risk on legitimate short answers is better understood (§19).
- A real `workflows/` entry externalizing the triage → search → answer
  sequence (§13).
