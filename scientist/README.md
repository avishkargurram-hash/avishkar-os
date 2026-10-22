# Scientist OS (Megha)

Durable, autonomous scientific-research engine for Avishkar OS. Delegated to
by Layla for `SCIENCE:` requests. Spec lives in the original design doc
(§1-§52); this file tracks **actual build status** as of 2026-10-15.

## Architecture (locked decisions)
- **D1**: Postgres is the workflow engine (`FOR UPDATE SKIP LOCKED` leasing, fenced completion). `orchestration/temporal_adapter.py` is a documentation-only stub for a future Temporal migration — never used in production.
- **D2**: Deploys on tv-mum-01 as `sci-api` (127.0.0.1:8095) + `sci-worker@` (systemd template, 2 instances).
- **D3**: Local 4B model does everyday work; Gemini/OpenRouter (Tier 3+) reserved for 7 named "key decision" purposes only (`models/router.py::PREMIUM_PURPOSES`), budget-capped.
- **D4**: Free literature sources first (OpenAlex, arXiv, Crossref, Semantic Scholar, PubMed).

## Build status (P0-P10)
| Phase | Scope | Status |
|---|---|---|
| P0-P5 | domain/config/storage/evidence/tools/models/mission/orchestration-engine layers | **Done** |
| P6 | `agents/handlers.py`, `agents/critics.py`, `core.py` (mission.cycle reconciler), `reports.py`, `runtime.py`, `orchestration/worker.py`, `demo.py` | **Done** (written, byte-compiled, import-verified up to the `avishkar-router` dependency boundary) |
| P7 | `api/app.py`, `api/auth.py` (FastAPI, SSE, approvals) | Not started |
| P8 | `web/index.html`, `cli.py`, `observability.py` | Not started |
| P9 | Layla integration (`SCIENCE:` loop, 4 tools, notifications outbox) | Not started |
| P10 | Deploy to tv-mum-01 (systemd units, sandbox Docker image, sudoers, live e2e run) | Not started |
| Tests | `tests/` (demo e2e, crash recovery, ScriptedProvider) | Not started |

**Not yet run end-to-end against a real database** -- needs `avishkar-router`
installed and a reachable Postgres 15+ with pgvector (`SCI_DATABASE_URL`).

## Known gaps (external audit, 2026-10-15)
- No `scientist/CONTRACT.md` yet.
- No SQLite fallback -- requires live PostgreSQL+pgvector.

## Entry points (once P7+ exist)
- `python -m avishkar_scientist.cli demo` -- run the zero-LLM demo mission end-to-end in-process.
- `uvicorn avishkar_scientist.api.app:app` -- the HTTP/SSE API.
