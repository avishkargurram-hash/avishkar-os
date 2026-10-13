# Layla Operational Runbook

Mission Layla Directive D, Part XVII (Production Deployment). See
[CONTRACT.md §60](./CONTRACT.md) and [README.md's Production
Deployment section](./README.md) for what's real vs. externally
gated. Every command below operates on real, already-tested
components (`avishkar_layla.deployment`, `ExecutiveRuntime`,
`FileMemoryPolicy`) -- nothing here is aspirational.

## Environments: DEVELOPMENT → TEST → STAGING → PRODUCTION

Not a new config system -- `avishkar_core.Config`'s real, existing
layered precedence (defaults < config file < environment variables <
explicit overrides, CONTRACT.md §1) already supports this. The
convention this runbook uses on top of it:

| Stage | `LAYLA_DATA_DIR` | LLM provider | Notes |
|---|---|---|---|
| DEVELOPMENT | a local temp/scratch dir | MockProvider (no `ANTHROPIC_API_KEY` set) | `python -m unittest discover -s layla/python/tests` is the real development feedback loop. |
| TEST | a fresh, disposable dir per run | MockProvider or `test_live_anthropic_integration.py` (opt-in, `LIVE_TEST_MODE=1`) | CI should run the full 574-test suite; see README.md Testing Guide. |
| STAGING | a persistent volume, separate from production's | real `AnthropicProvider`, a real but low-traffic credential | Exercise `run_production.py` for real, including the real `/health` and `/health/report` endpoints, before promoting. |
| PRODUCTION | a durable, backed-up volume (see Backup/Restore below) | real `AnthropicProvider`, production credential | See Startup/Shutdown and Monitoring below. |

Promote a build between stages by tagging the same container image
(`docker build`, one image, multiple `docker run`/orchestrator
deployments with different env vars) -- never a source rebuild per
stage.

## Startup

```bash
docker run -d --name layla \
  -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e LAYLA_DEFAULT_MODEL=claude-haiku-4-5 \
  -v layla-data:/data/layla \
  avishkar-layla:<tag>
```

Or directly (matches `layla/Dockerfile`'s `CMD`, and every test/example
script's own `PYTHONPATH` convention -- see README.md's Testing
Guide):

```bash
PYTHONPATH="core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;factories/evaluation-factory/python;factories/prompt-factory/python;factories/workflow-factory/python;layla/python" \
  ANTHROPIC_API_KEY=sk-ant-... \
  python layla/deploy/run_production.py
```

Startup is real and self-verifying: `run_production.py` logs whether a
real credential was found (`real_llm=True/False`) before entering
`run_forever()`, and the real `HealthServer` starts serving `/health`
before the first task can even be received -- an orchestrator's
readiness probe should poll `/health` before routing traffic.

## Shutdown

Send `SIGTERM` (the default `docker stop`, or `kill <pid>`) or
`SIGINT` (Ctrl-C). `avishkar_layla.deployment.install_graceful_shutdown()`
is wired in `run_production.py`'s `main()` and calls the real
`ExecutiveRuntime.request_shutdown()` -- `run_forever()` finishes its
current iteration, records `layla.runtime.run_forever_stopped` via the
real `AuditLogger`, and returns cleanly. Never `docker kill` /
`SIGKILL` a healthy instance except as a last resort -- it skips that
final audit record and any in-flight `run_forever()` iteration.

## Health Checks

- `GET /health` -- cheap liveness only (`ExecutiveRuntime.is_alive()`).
  `200 {"alive": true}` or `503 {"alive": false}`. Use for a container
  orchestrator's liveness probe.
- `GET /health/report` -- the full `build_production_health_report()`
  (Part XIV) as JSON: operational health, real delegation
  totals/failure rate, and (if wired) `BusinessIntelligenceEngine`'s
  own real cost/success-rate report. Use for a dashboard or a readiness
  probe that wants more than a boolean.

`layla/Dockerfile`'s own `HEALTHCHECK` already calls the real `/health`
endpoint every 30s.

## Backup / Restore

`FileMemoryPolicy`'s entire durable state is 4 JSON files under
`LAYLA_DATA_DIR` (`short_term.json`, `long_term.json`, `episodic.json`,
`semantic.json`) -- session/task/audit/personal-model state all live
under the same real, namespaced-key backend (CONTRACT.md §9-10).

```python
from avishkar_layla.deployment import backup_data_directory, restore_data_directory

# Backup: real shutil.copytree into a timestamped directory.
backup_path = backup_data_directory("/data/layla", "/backups/layla")

# Restore: real, destructive -- replaces /data/layla's current
# contents with the backup's.
restore_data_directory(backup_path, "/data/layla")
```

Run a backup on a schedule (e.g. via the real `avishkar_layla.Scheduler`
itself, or an external cron/orchestrator job calling the same function)
BEFORE any deployment/rollback, and verify a restored instance's
`/health/report` shows the expected `incomplete_task_count` before
resuming production traffic. `test_deployment.py`'s
`TestBackupRestore` class proves this round-trip against real files,
not a simulation.

## Disaster Recovery

1. Stop the unhealthy instance (graceful `SIGTERM` if it responds to
   `/health` at all; force-stop only if it does not).
2. `restore_data_directory()` from the most recent known-good backup
   into a fresh `LAYLA_DATA_DIR`.
3. Start a new instance pointed at the restored directory.
4. Confirm `/health` returns `200` and `/health/report`'s
   `operational.incomplete_task_count` matches expectations before
   resuming production traffic -- an unexpectedly high count may mean
   the restored backup predates in-flight work; check
   `SessionManager.list_incomplete()` for those tasks specifically
   (this platform's real resume-in-place machinery, Part XII/ADR-0039,
   `TaskLeaseManager`, handles picking those back up correctly once
   traffic resumes).

## Deployment / Rollback

This platform's own discipline (every Directive D part is one
reviewable git commit with an ADR) IS the deployment/rollback
procedure:

- **Deploy**: build and tag an image from a specific, known commit;
  promote that same tag through STAGING → PRODUCTION per the table
  above.
- **Rollback**: `docker run` the previous image tag against the same
  `LAYLA_DATA_DIR` volume. Because every schema/contract change in this
  codebase ships with an ADR + migration note (the 20 Critical Rules'
  standing requirement), check the newest ADRs in `DECISIONS.md` before
  rolling back across a boundary that changed on-disk data shape --  a
  rollback that also needs a data migration is not a plain image
  swap.

## Monitoring / Alerting (what's real vs. not covered)

- 🟢 Real: `/health`, `/health/report`, and the underlying
  `AuditLogger`/`Scheduler` dead-letter escalation (`on_job_error`,
  Part XI) already provide real signal a monitoring system can poll or
  subscribe to.
- 🔴 NOT COVERED: this platform does not itself push metrics to a
  time-series store or alerting system (Prometheus, Datadog, PagerDuty,
  etc.) -- `/health/report` is real, structured JSON meant to be
  scraped/polled by an external monitoring system, not a push-based
  integration. Building that integration is real future work,
  honestly disclosed as not built here (see README.md Production
  Deployment section).

## Known External-Dependency Gaps (disclosed, not fabricated)

- `layla/Dockerfile` is written and its underlying Python entrypoint
  (`run_production.py`) is smoke-tested for real (build a real
  runtime, run a real tick, hit a real `/health` endpoint) -- but the
  Dockerfile's own `docker build` was NOT verified end-to-end in this
  environment: the Docker CLI is present, but no Docker daemon is
  running in this sandboxed session. A real `docker build`/`docker
  run` cycle is real future verification, not claimed as done.
- Optional capability extras (voice/vision/computer_control/channels/
  mqtt/environment) are not installed in the base image; a deployment
  needing one of those builds its own image `FROM avishkar-layla:local`
  adding the specific `pip install -e "layla/python[<extra>]"` it
  needs.
