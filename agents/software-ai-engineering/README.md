# Software & AI Engineering — Chief Domain Agent

Built on [Agent Framework](../../factories/agent-factory/README.md) per
[DECISIONS.md](../../DECISIONS.md) ADR-0010 — a complete software
system, not a system prompt. Package: `blueprint.json` +
[`python/software_ai_engineering_agent.py`](./python/software_ai_engineering_agent.py).
Documented to [STANDARDS.md](../../STANDARDS.md) §2.3's 30-section
template.

## 1. Identity & Mission

I am the engineering judgment this platform applies to its own code and
every product built on it. My mandate: design, build, review, and debug
software and AI systems to production-quality standards — correct,
secure, maintainable, and no more complex than the problem requires. I
do not ship what I can't defend under review, and I do not gold-plate
what doesn't need it.

## 2. Responsibilities

- Architecture and design decisions with explicit trade-offs stated, not
  hidden in the implementation.
- Code review: correctness, security, maintainability, and whether the
  change matches its stated intent.
- Debugging: root-causing failures, not just making symptoms disappear.
- Complexity management: flagging when a design is over- or
  under-engineered for what it actually needs to do.
- I do **not** own product/business decisions (that's Startup, Business &
  Product's domain) or infrastructure provisioning policy (a future
  `infra-factory` concern, ARCHITECTURE.md §1) — I advise on technical
  feasibility, I don't set product priority.

## 3. Domain Knowledge Architecture

My knowledge is organized in three layers: (1) platform-specific —
this repository's own `ARCHITECTURE.md`, `STANDARDS.md`, and
`DECISIONS.md`, which I treat as binding, not advisory; (2)
engineering-general — SOLID, Clean Architecture, DRY/KISS/YAGNI, the
principles STANDARDS.md §1 already commits this platform to; (3)
task-specific — whatever code, docs, or specs a given task hands me via
`Task.context`. No dedicated `knowledge/` base exists yet
(ROADMAP.md Phase 6, Knowledge Framework) — until then, layers 1–2 live
in this README and the domain module's guardrail/quality-gate logic, and
layer 3 is caller-supplied per task.

## 4. Reasoning Strategies

I don't run one fixed script — I rotate through the strategies declared
in my blueprint (`reasoning_strategies`), because different engineering
questions call for different structuring:

- **Architecture / design** questions get first-principles reasoning —
  I don't default to "how similar systems usually solve this."
- **Cross-cutting / infrastructure** questions get systems thinking —
  I look for the feedback loop or second-order effect a local fix would
  miss.
- **Technology/approach choices among real alternatives** get the
  decision-matrix strategy (see §5).
- **Debugging** gets the scientific method — a falsifiable hypothesis
  about the failure, not a guess-and-check loop.

All four are genuinely used, not declared for completeness — see
`agent-factory`'s Best Practices note against padding a blueprint with
unused strategies.

## 5. Decision Frameworks

For competing technical approaches, I use the `decision_matrix` thinking
model, weighing candidates against explicit criteria (default:
correctness, cost, maintainability — overridable per task via
`context["decision_criteria"]`). I escalate rather than decide when: the
trade-off is really a product/business call (routed to Startup, Business
& Product via the Orchestrator), or the decision needs information I
don't have (I say so, I don't guess).

## 6. Thinking Models

First principles, systems thinking, scientific method, and decision
matrix — see `factories/agent-factory/python/avishkar_agent/thinking.py`
for the reference implementations these are built from, and §4 above for
when each applies.

## 7. Planning & Reflection

Every task runs the Agent Framework's plan → act → reflect loop
(`ChiefDomainAgent.handle`, up to `blueprint.max_iterations = 4`): plan
with the iteration's thinking strategy, act by calling the AI Router for
a completion framed by that plan, reflect on whether the result actually
answers the task. A failing quality gate (§19) triggers another
iteration if budget remains; exhausting the budget without passing marks
the task `"failed"` rather than returning a result I haven't actually
vetted.

## 8. Memory Policies

Backed by `InMemoryMemoryPolicy` (blueprint `memory_policy.backend =
"in_memory"`) — process-local, non-persistent, per
`memory-factory`'s not-yet-built status (ROADMAP.md Phase 5). Intended
use once persistent backends exist: `short_term` for the current task's
working context, `long_term` for durable facts about a codebase I
revisit, `episodic` for specific past incidents ("this service had a
memory leak in module X"), `semantic` for generalized lessons ("this
team's services tend to under-specify timeouts"). Today, none of this
survives past one process's lifetime — see Limitations.

## 9. MCP Integration Points

Declared via `MCPToolRef`, not yet resolvable (mcp-factory is
ROADMAP.md Phase 4): `mcp:github/get_file_contents` and
`mcp:github/create_pull_request`. Calling either today raises
`MCPServerNotAvailableError` — a clear, typed failure, verified in
[`tests/test_software_ai_engineering_agent.py`](./tests/test_software_ai_engineering_agent.py).
No blueprint change will be needed once Phase 4 ships.

## 10. Tool Registry

Two real, callable tools today (`python/software_ai_engineering_agent.py`):

- **`static_check(code: str) -> list[str]`** — flags `print()` calls,
  bare `except:`, and `TODO`/`FIXME` markers. A small, honest heuristic,
  not a full linter (see Limitations).
- **`estimate_complexity(code: str) -> int`** — a naive cyclomatic-
  complexity-style count (1 baseline + one per control-flow keyword) —
  a cheap signal for "does this need splitting," not a certified metric.

Both are unit-tested directly and reachable via `agent.tools.call(name, input)`.

## 11. Knowledge Sources

This repository's own governance docs (`ARCHITECTURE.md`, `STANDARDS.md`,
`DECISIONS.md`), general software engineering literature, and whatever
source code/specs a task supplies via `Task.context`. No external search
or retrieval tool is wired yet (would be an MCP integration — §9 — once
`mcp-factory` ships).

## 12. Prompt Library

v1 does not maintain a separate prompt-template file library —
`ChiefDomainAgent._act` builds one structured prompt per iteration from
`blueprint.mission` + the task + the current thinking step's framing
(see `agent-factory/python/avishkar_agent/agent.py`). A dedicated,
versioned prompt library is `prompt-factory`'s job (ROADMAP.md Phase 8);
until then, the prompt construction logic itself is this agent's "prompt
library," and it's small enough to read directly rather than fragment
across files.

## 13. Workflow Library

No standalone `workflows/` entry yet (Phase 7, Workflow Framework, isn't
built). The natural first workflow this agent will participate in is a
**code review workflow**: static_check → estimate_complexity →
model-assisted review → quality gates — which today runs as one
`handle()` call's internal loop, and will externalize into a real
`workflows/` entry once Workflow Framework exists to host it.

## 14. Template Library

No standalone output-template library yet (would be `template-factory`,
Phase 8). Output shape today is governed by §21 (Output Standards)
directly.

## 15. Checklists

Pre-merge checklist this agent applies conceptually during review (not
yet a separate machine-checkable artifact — see §14):

- [ ] No `print()`/bare `except:`/`TODO` left in changed code (`static_check`)
- [ ] No function's complexity estimate spikes without a stated reason
- [ ] Change matches its stated intent — no silent scope creep
- [ ] No secret, credential, or destructive command present unguarded
- [ ] Public functions/classes have purpose-stating docstrings
      (STANDARDS.md §4)

## 16. Evaluation Framework

Today: the quality gates in §19, hand-written `QualityGate` callables.
`evaluation-factory` (deferred, ADR-0009) will replace this with a real
harness and scored eval sets — this agent's `blueprint.quality_gates`
names are the seam that integration will attach to, per `agent-factory`
README's Future Roadmap.

## 17. Security Policies

Never asked to handle or echo a credential — the `no-secrets-in-task`
guardrail (§18) blocks that class of task before any model call, not
after. Never executes anything; I recommend and review, I don't run
arbitrary code myself (no `bash`-equivalent tool is registered).

## 18. Guardrails

Two, both pre-execution (`python/software_ai_engineering_agent.py`):

- **`no-secrets-in-task`** — blocks a task whose input names a password/
  API key/secret token/private key directly.
- **`no-destructive-commands`** — blocks `rm -rf`, `git push --force`,
  `DROP TABLE`, `--no-verify`, and similar irreversible actions; these
  require explicit human approval (via an `ApprovalGate`, not yet wired
  by default on this agent — see Limitations), not autonomous execution.

## 19. Quality Gates

Two, both post-execution:

- **`minimum-substance`** — output must be at least 10 non-whitespace
  characters (catches an empty or near-empty response).
- **`no-placeholder-output`** — output must not contain "lorem ipsum",
  "TODO", "FIXME", or "TBD" — a response that's still a placeholder isn't
  done.

A task that fails a gate on every iteration up to `max_iterations` ends
`"failed"`, not silently returned as if it succeeded — verified in
`test_quality_gate_rejects_placeholder_output`.

## 20. Error Recovery Strategies

A failing quality gate triggers another plan-act-reflect iteration
(§7) rather than surfacing a half-formed answer. A blocked guardrail or
denied approval gate returns immediately with `status="blocked"` and a
`blocked_reason` — the caller gets an explicit, actionable signal, not an
exception to catch. There is currently no retry-with-backoff for AI
Router failures at the agent level — `Router` itself already does
provider fallback (see `router/README.md`); a router-level
`NoAvailableProviderError` currently propagates out of `handle()`
uncaught, which is an honest gap tracked in §30.

## 21. Output Standards

A design/review response states the recommendation, the reasoning behind
it (visible in `thinking_trace`, not just asserted), and — for
architecture questions — the trade-off explicitly, per the decision
matrix criteria in play. No placeholder text (enforced by §19). No
unrequested scope expansion — the response answers what was asked.

## 22. Communication Style

Direct, technical, and willing to disagree with the premise of a task if
the premise is wrong (e.g., a task assuming a fix that would paper over
the actual bug). No padding, no hedging language where a plain answer is
warranted — matching STANDARDS.md §1's own engineering register.

## 23. Collaboration Protocols

Reachable through `Orchestrator.route()` (task_type `"software"` or a
domain-substring match on "Software & AI Engineering"), participates in
`delegate_team()`/`broadcast()` alongside other Chief Domain Agents (see
`factories/agent-factory/examples/quickstart.py` for a working
Software-Engineering + Legal-Compliance pairing). When a task is really a
product or legal question, I say so rather than answering outside my
mandate (§2).

## 24. Sub-Agent Architecture

Four internal expert roles, absorbed rather than spun up as separate
top-level agents (ARCHITECTURE.md §4): **architect** (design/trade-off
questions), **reviewer** (code review), **debugger** (root-causing
failures), **security-auditor** (security-specific review). Routed via
`ChiefDomainAgent.route_to_sub_agent_role`, using the framework's default
keyword-matching router (normalizing hyphens on both the role name and
the task text — a real bug this agent's own quickstart example caught
and which is now regression-tested in `agent-factory`'s test suite).

## 25. Extensibility Model

New tools: register a `Tool` or `MCPToolRef` in `_build_tool_registry()`.
New guardrails/quality gates: add a function + register it in the
matching `_build_*()` helper. None of this touches `avishkar_agent`
itself — see `agent-factory` README's Extension Model, which this agent
is the proof case for.

## 26. Testing Strategy

Unit tests for every tool function and guardrail in isolation
(`test_static_check_tool`, `test_estimate_complexity_tool`,
`test_guardrails`), plus integration tests running the full
`ChiefDomainAgent.handle()` loop against `MockProvider` (no network, no
API key) covering: normal completion, both guardrails, the placeholder
quality gate exhausting iterations to `"failed"`, direct tool calls, the
declared-but-unresolvable MCP tools, and sub-agent routing. 19 tests, all
passing — see [`tests/`](./tests/).

## 27. Versioning Strategy

`blueprint.json.version` follows semver (currently `0.1.0`). A breaking
change to this agent's mission, guardrails, or quality gates bumps the
minor version at minimum; a genuinely new capability (a new tool, a new
sub-agent role) is a minor bump; a bug fix to existing behavior (like the
hyphen-normalization fix in §24) is a patch bump. No automated version
enforcement exists yet — tracked honestly as a gap, not a false claim.

## 28. Documentation

This README is the primary source. Deeper design notes, if they outgrow
this file, belong in `docs/` (ARCHITECTURE.md §3), not scattered into
this agent's own directory.

## 29. Examples

```bash
python agents/software-ai-engineering/examples/quickstart.py
```

Runs, on `MockProvider`: a full design-task reasoning loop with visible
`thinking_trace`; both real tools called directly; a declared MCP tool
failing with a clear typed error; a guardrail blocking a destructive-
command request before any model call; and sub-agent routing to
`security-auditor`. Output is deterministic and requires no API key.

## 30. Future Roadmap

- **Real static analysis** — `static_check`'s three heuristics are
  honest but shallow; a real linter integration (via a future `Tool` or
  MCP server) replaces them without changing this agent's guardrail/
  quality-gate contracts.
- **`ApprovalGate` for destructive actions** — today `no-destructive-
  commands` hard-blocks; a future version routes these to human approval
  (`ApprovalGate(policy="always_ask")`, already supported by
  `agent-factory`) instead of an unconditional block, once there's a
  concrete approval workflow to wire it to.
- **Router-failure recovery at the agent level** — see §20's gap.
- **Real `knowledge/`, `memory/`, `mcp/`, `workflows/`, `templates/`
  wiring** once Phases 4–8 ship — every seam already exists (§8, §9,
  §12, §13, §14); this is integration work, not redesign.
- **`evaluation-factory` scoring** replacing the hand-written quality
  gates in §16/§19.
