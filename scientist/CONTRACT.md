# Scientist OS Contract

## 1. System Topology & Architecture

Scientist OS is an autonomous, hypothesis-driven scientific research engine that operates in a distributed pairing between **tv-mum-01** (heavy compute, queue workers, local models, and PostgreSQL with pgvector) and **Oracle** (Layla's conversational brain).

```
                      +---------------------------------------+
                      |       Oracle Cloud (129.225.72.80)    |
                      |  Layla Conversational Brain (:8100)   |
                      |  - layla_scientist.py Brain Plugin    |
                      |  - 4 Executive Research Tools         |
                      +-------------------+-------------------+
                                          |
                        Bearer Token Auth | HTTP REST / SSE
                        Port 8095 (UFW)   |
                                          v
                      +---------------------------------------+
                      |         tv-mum-01 (103.168.22.202)    |
                      |                                       |
                      |  sci-api (:8095) FastAPI Server       |
                      |  sci-worker@1, sci-worker@2 (Queues)  |
                      |  sci-supervisor (Task Reconciler)     |
                      |  sci-postgres (:5433, pgvector/pg16)  |
                      |  Local LLM / Embed (8081/8082)        |
                      |  sci-sandbox (Isolated Docker Run)    |
                      +---------------------------------------+
```

---

## 2. Security & Sandboxing Contract

1. **Host Isolation**: All Scientist OS processes on `tv-mum-01` run under the non-privileged service user `sci:sci` (UID/GID 995:987). Secrets in `/opt/scientist/secrets/scientist.env` are restricted to `0600` permissions.
2. **Experiment AST Static Analysis**: Prior to execution, all model-generated experimental code is analyzed via `ast.parse()`. Star-imports, dunder attributes (`__class__`, etc.), network sockets, filesystem I/O, and process spawn imports are rejected statically (`REJECTED_STATIC`).
3. **Execution Sandbox**: Sandboxed code runs inside `sci-sandbox:latest` (Debian bookworm slim with scientific packages) via `/usr/local/bin/sci-sandbox-run`:
   - `--network none` (Strictly zero network access)
   - `--read-only` (Host and container root filesystems are read-only)
   - `--memory 512m --cpus 1` (Resource bounds)
   - `--pids-limit 64` (Fork bomb prevention)
   - `--user 65534:65534` (Nobody user, non-root)
   - `--cap-drop ALL --security-opt no-new-privileges` (Kernel capabilities stripped)
   - Read-only job mount at `/sandbox:ro`
4. **Execution Privileges**: Sudoers entry `/etc/sudoers.d/sci-sandbox` allows only `sci ALL=(root) NOPASSWD: /usr/local/bin/sci-sandbox-run`.

---

## 3. API & Authentication Contract

The FastAPI service binds to `0.0.0.0:8095` with token-bucket rate limiting (60 req/min per token) and Bearer token authentication:

- **Tokens Configured**:
  - `owner:sci_sec_token_...:owner` (Full administrative and execution control)
  - `layla:sci_layla_token_3e4d5f6a:owner` (Executive integration token for Layla Brain)
  - `viewer:sci_view_token_...:viewer` (Read-only access for dashboards and telemetry)

### Endpoints
- `GET /healthz`: Public service health and database ping.
- `POST /api/missions`: Launch new research mission (Role: `owner`).
- `GET /api/missions`: List 50 most recent missions (Role: `viewer`).
- `GET /api/missions/{id}`: Detailed mission record (Role: `viewer`).
- `GET /api/missions/{id}/status`: Live phase, stage, iteration, confidence (Role: `viewer`).
- `GET /api/missions/{id}/evidence`: Collected empirical evidence items (Role: `viewer`).
- `GET /api/missions/{id}/claims`: Formulated scientific claims (Role: `viewer`).
- `GET /api/missions/{id}/experiments`: Synthetic experiment execution records (Role: `viewer`).
- `GET /api/missions/{id}/verdict`: Bayesian synthesized verdict and conclusion (Role: `viewer`).
- `GET /api/missions/{id}/report`: Full Markdown report (Role: `viewer`).
- `GET /api/missions/{id}/events`: Live SSE event stream via PostgreSQL `LISTEN sci_events`.
- `POST /api/missions/{id}/pause|resume|cancel`: Lifecycle control (Role: `owner`).
- `GET /`: Single-page dark mode dashboard (`index.html`).

---

## 4. Layla Executive Brain Plugin Contract

Layla serves as the **Executive Commander** of Scientist OS, delegating complex research inquiries without burdening her conversational turn loop:

- **Plugin Location**: `/opt/layla/layla_scientist.py`
- **Patch Script**: `/opt/layla/patch_scientist.py`
- **Kill Switch**: `SCIENTIST=0` in `/opt/layla/.env` cleanly disables the plugin and returns calm explanatory messages without raising exceptions.
- **Tools Declared**:
  1. `start_scientific_research(question, depth="STANDARD")`
  2. `get_research_status(mission_id)`
  3. `get_research_verdict(mission_id)`
  4. `get_research_report(mission_id, format="markdown")`
- **Turn Hinting**: Injects context hints when the user mentions an active `SCI-...` mission or discusses scientific validation.

---

## 5. Storage, Migration & Backup Contract

- **Database**: PostgreSQL 16 running in `sci-postgres` Docker container on `127.0.0.1:5433` with `pgvector 0.8.7`.
- **Database URL**: `postgresql://sci:7a714c8a14fd4ebc1b649ff612f8bda351bb1140d3de3da0@127.0.0.1:5433/scientist`
- **Tables (30)**: `missions`, `hypotheses`, `tasks`, `task_attempts`, `evidence`, `claims`, `experiments`, `experiment_runs`, `replications`, `critic_reports`, `verdicts`, `reports`, `events`, `provenance`, `model_calls`, `tool_calls`, `notifications`, `approvals`, `audit_log`, `budgets`, `documents`, `sources`, `datasets`, `contradictions`, `research_states`, `http_cache`, `result_cache`, `semantic_cache`, `users`, `schema_migrations`.
- **Backup**: Crash-consistent binary dumps via `docker exec sci-postgres pg_dump -U sci -Fc scientist` integrated into `/opt/layla365/backup.sh`, encrypted with Age, and mirrored offsite to Oracle Cloud.
