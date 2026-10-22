# Scientist OS — Architecture Mapping & Implementation Plan

Status: PROPOSAL (no code written yet). Spec section 53 requires this before any build.
Date: 2026-10-15. Owner persona: Megha (researcher). Executive: Layla.

## 1. What already exists (inspected)

| Need (spec) | Existing component | Verdict |
|---|---|---|
| Config / logging / event bus | `core/python/avishkar_core` — layered `Config`, JSON logger, `EventBus` (in-process, synchronous, no persistence), `ModuleRegistry` | REUSE config + logger. Event bus is NOT durable -> add persisted `sci.events` outbox that also publishes to it. |
| Model router | `router/python/avishkar_router` — `Router.route()`, `RoutingPolicy`, providers (Anthropic, OpenAI-compatible, Mock), fallback chain, in-memory `CostTracker` per caller | REUSE as the provider layer. Add a thin `TierRouter` on top (tier 0-4, info-gain, budget gate) and a persisted `model_calls` ledger. Router itself untouched. |
| Tool registry / MCP | `factories/mcp-factory` — `UniversalToolRegistry`, `ToolRuntime`, MCP + REST adapters, policies | REUSE. Scientist tools register as `ToolContract`s; add `permissions`, `cost`, `security_policy` via contract metadata. |
| Memory / embeddings / cache | `factories/memory-factory`, `factories/knowledge-factory` (chunker, embedder, index); Layla365 Qdrant + local BGE-M3 (:8082) | REUSE embedder + chunker. Semantic cache = pgvector table (spec: pgvector first). |
| Auth / roles / approvals | `layla/.../auth.py` (`AuthorizationManager`), `approval.py` (`ApprovalManager`), L365 `core.approvals` + Telegram approval cards | REUSE for HITL (`WAITING_FOR_HUMAN`). Service API uses bearer tokens like the L365 gateway. |
| Scheduling / dead-letter / leases | `layla/.../scheduler.py` (dead-letter), `task_lease.py` (`TaskLeaseManager`, stale-task recovery) | REUSE the lease *design*; Postgres `SELECT ... FOR UPDATE SKIP LOCKED` is the real durable queue. |
| Workflow | `factories/workflow-factory` — in-memory `WorkflowEngine`, steps, max-steps guard. No persistence. | NOT durable -> insufficient. See decision D1. |
| Layla delegation | `layla365/gateway` (Oracle brain `/agent/gateway`: verbs heartbeat/inbox/report/request, per-agent token, allowlist, rate limit, audit); Layla tools `assign_agent_task`, `agent_reports` | EXTEND: add actions `science.start/status/verdict/report` + Layla tools. |
| Megha today | `layla365/l365/duties.py::megha_digest` — one web.search + one 4B-model summary, daily 14:30 IST (not 09:00) | KEEP as a cheap daily digest; optionally let it spawn a QUICK mission. |
| Database | Postgres 16 on tv-mum-01 with per-agent roles + RLS (`layla365` db), Qdrant 1.19 | REUSE the server; new schema `sci` in a new db `scientist` (isolation from agent DB). |
| Observability | `layla/.../observability.py`, `monitoring.py`, JSON logger | REUSE logger; add `mission_id`/`trace_id` fields. |
| Sandbox | none for model-generated code (Docker is installed on tv-mum-01) | BUILD (Phase 5). |

## 2. Hard constraints found (they shape the design)

1. **Owner rule (2026-10-12): Layla365 agents think ONLY with the local Qwen3-4B; Cerebras is Layla's.** **OVERRIDE (2026-10-15, owner): Megha / Scientist OS uses Gemini instead of the local 4B. Other 8 agents unchanged (local only).** Key lives only in `scientist/.secrets/gemini.env` (gitignored) and, at deploy, a 600 env file readable only by the sci services. Tier mapping (verified live 2026-10-15): T0 = no model (rules/cache); T1 = local Qwen/BGE (embeddings, trivial); T2 = `gemini-3.7-flash` (HTTP 200, ~6s); T3 = `gemini-3.8-flash` (503 under demand -> fallback to 3.7-flash); T4 = `gemini-3.1-pro-preview` (**429 quota exceeded on this key** -> disabled until billing/quota enabled). `gemini-2.5-*` return 404 for this key (retired for new users) - do not use.
2. **tv-mum-01 is small** (4 GB swap, local 1.5B/4B + BGE-M3, Postgres, Qdrant). Temporal server (+its own DB, ~1-2 GB) is not practical there.
3. **Quiet hours 05:00-14:00 IST:** missions keep running, but notifications/approval cards are held until 14:00.
4. **Repo rule:** Avishkar OS holds no product logic. Scientist OS is a generic research engine -> passes the "would a second product want it?" test, so it lives as a new framework `scientist/`, with CONTRACT.md + README per STANDARDS.md and an ADR (next free: ADR-0046).
5. Telegram + approvals already exist -> reuse, don't rebuild.

## 3. Decisions needing the owner (my recommendation first)

- **D1 Workflow engine.** Recommend a **Postgres-backed durable workflow engine behind a `WorkflowEngine` interface** (leases, heartbeats, retries, checkpoints, pause/resume/cancel, crash recovery), with a Temporal adapter stubbed for later. Spec explicitly allows this when Temporal isn't practical. Alternative: run Temporal on a bigger box — more moving parts, no benefit at this scale.
- **D2 Where it runs.** Recommend tv-mum-01 beside `l365-runner`: services `sci-api` (FastAPI + SSE) and `sci-worker` (N processes). Layla reaches it through the existing gateway. Alternative: Oracle VM — rejected (only ~950 MB RAM).
- **D3 Premium budget.** Recommend default `premium_model_budget = 0`, Tier 3 via Layla-think capped per mission. Tell me if you want to attach a frontier API key later.
- **D4 Web/academic sources.** Free first: arXiv, Crossref, OpenAlex, Semantic Scholar, PubMed (all keyless or free-key). Layla's `web.search` via gateway for general web.

## 4. Package layout (modular monolith)

```
Avishkar-OS/scientist/
  CONTRACT.md  README.md  ARCHITECTURE_MAPPING.md
  python/avishkar_scientist/
    mission/ planner/ scientist_core/ state/ termination/ verdict/ reports/
    orchestration/ (WorkflowEngine iface, PgWorkflowEngine, dispatcher, queues, TemporalAdapter stub)
    agents/ (research literature data experiment analysis critic replication workers)
    models/ (TierRouter, ModelBudget, caches, local/layla-think providers)
    tools/ (registry adapters, arxiv/crossref/openalex/semanticscholar/pubmed, python sandbox)
    evidence/ (store, claims, provenance, contradiction, independence, confidence)
    storage/ (postgres migrations, pgvector, object store [filesystem now, S3-compatible later], redis cache)
    events/ security/ observability/ integrations/{layla,avishkar_os}
    api/ (FastAPI + SSE)  demo/ (SCI-DEMO-001)
  web/  (single-page UI: ask box, depth, mission card, optional live activity)
  python/tests/
```

## 5. Phases (each ends with tests passing + docs)

- **P0** ADR-0046, CONTRACT/README, Postgres schema `sci` (all 20+ tables from spec 32), migrations runner.
- **P1 (end-to-end, mock tools, DEMO mode):** Mission model, ResearchState, Planner (DAG), PgWorkflowEngine + queues + workers, Scientist Core loop, Evidence store, Termination, Verdict, Report, REST API + SSE, minimal UI, restart-recovery test. Definition: SCI-DEMO-001 runs question -> report with zero LLM spend.
- **P2** Real sources (arXiv/Crossref/OpenAlex/S2/PubMed), document cache, dedup by content hash, claim extraction with local model.
- **P3** TierRouter + ModelBudget + semantic/result caches, local Qwen tiers.
- **P4** Layla-think tier, verdict council (A/B/C judges) for DEEP/EXTREME.
- **P5** Docker sandbox (no network, CPU/mem/pids/time limits, read-only fs) + static code validation.
- **P6** Experiment/simulation engine, data-analysis workers (numpy/scipy/statsmodels), `PHYSICAL_EXPERIMENT_REQUIRED` handling.
- **P7** Critics (6 roles), contradiction engine, independent replication.
- **P8** Provenance graph, source-lineage independence scoring, Research Quality Score.
- **P9** Layla integration: gateway actions + Layla tools `start_scientific_research / get_research_status / get_research_verdict / get_research_report`, Telegram milestone notifications (quiet-hours aware), Megha duty hook.
- **P10** Deploy on tv-mum-01 (systemd, backups, auth, rate limits, worker scale-out), observability dashboards.

## 6. Integrity rules baked into the design

No fabricated papers/numbers: every claim row requires a `source_id` or `experiment_run_id` (DB CHECK constraint). Numeric results come only from sandboxed code or tool output. Epistemic status enum FACT/OBSERVATION/INFERENCE/HYPOTHESIS/SPECULATION on every claim. Independence: confidence counts distinct lineage roots, not documents. Verdict Engine reads a frozen evidence package and never calls the planner.

## 7. Honest limits

Gemini flash-class models carry reasoning; the pro tier is currently blocked by quota (429), and 3.8-flash can 503 under load, so the provider needs retry + fallback chain (3.8 -> 3.7 -> flash-latest) and a persisted per-mission token ledger. Until pro quota exists, DEEP/EXTREME verdicts will say so in their uncertainty. Gemini key was pasted in chat: rotate it. Physical experiments are never simulated as real.
