# Live Integration Guide — Layla ↔ real Anthropic API (Priority 17.5, ADR-0025)

Every test in Avishkar OS, including all 189 Layla tests through
Priority 17.4, runs offline against dependency-injected fakes (a
`MockProvider`, a fake MCP session, a fake HTTP transport). That is
good test hygiene, but it means no test has ever proven the full path
from a Layla task to a real model response and back. This guide
documents the one, narrow, opt-in exception.

## What this validates

```
ExecutiveRuntime.handle_event()
  -> Planner (real capability inference)
  -> DelegationEngine.delegate()
  -> a real ChiefDomainAgent
  -> a real avishkar_router.Router
  -> the real AnthropicProvider
  -> the live Anthropic Messages API
  -> a real ProviderResponse (content, tokens, cost, request_id)
  -> ResultValidator
  -> ExecutiveSynthesizer
  -> LaylaTask.state == COMPLETED
```

Every piece of that chain except the final network call was already
real in Phase 16. This is the first time the network call is real too.

## What this does NOT do

- Does not send a real email, Slack message, or any external
  communication.
- Does not create, modify, or delete any record anywhere.
- Does not perform any financial, legal, or destructive operation.
- Does not touch `DelegationEngine`'s write-classified idempotency path
  or trigger an `ApprovalManager` gate — the test's own task is
  deliberately phrased as a read-only, LOW-risk request.
- Does not run by default. `python -m unittest discover` on this
  repository never makes a network call unless you explicitly opt in
  exactly as described below.

## Prerequisites

1. The `anthropic` Python package installed:
   ```bash
   pip install anthropic
   ```
   (or the `avishkar-router[anthropic]` extra, if defined in
   `router/python/pyproject.toml`).
2. A real Anthropic API key with a small amount of available credit.
   **Never commit this key.** Set it as an environment variable only,
   never as a literal in code, a config file, or a commit.

## Exact execution instructions

**Windows PowerShell:**
```powershell
$env:LIVE_TEST_MODE = "1"
$env:ANTHROPIC_API_KEY = "sk-ant-...your real key..."
$env:PYTHONPATH = "core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;layla/python"
python -m unittest layla.python.tests.test_live_anthropic_integration -v
```

**Bash / Git Bash:**
```bash
LIVE_TEST_MODE=1 ANTHROPIC_API_KEY="sk-ant-...your real key..." \
  PYTHONPATH="core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;layla/python" \
  python -m unittest layla.python.tests.test_live_anthropic_integration -v
```

Unset either variable (or run the normal test suite without setting
them) and the test **skips** — printed as `ok (skipped=1)` — rather
than failing or fabricating a pass. This is intentional: absence of
credentials is not a bug, it's the default, safe state.

## What a successful run prints

```
--- Live Anthropic integration result ---
  task.state:        COMPLETED
  task.result:       '[diagnostics-agent]: OK'
  cost_usd (audit):  0.0002...
  cost_usd (router): 0.0002...
------------------------------------------
```

The exact `task.result` text depends on the live model's actual
response (it is asked to reply with exactly "OK", but nothing forces
that beyond the prompt itself — this is a real, non-deterministic
external call, not a scripted fixture).

## Cost

One run costs a small fraction of a cent: `claude-haiku-4-5` at
$1.00/$5.00 per million input/output tokens, `max_tokens=32`, a ~20
token prompt. The test itself asserts the actual reported cost is
under `$0.01` and fails loudly (not silently) if it somehow isn't —
see `_MAX_ACCEPTABLE_COST_USD` in the test file.

## Verified status as of this priority's own commit

This infrastructure was built and the skip path (no credentials
present) was verified to work correctly. **A successful live run
against the real Anthropic API was NOT performed as part of this
priority** — no `ANTHROPIC_API_KEY` was available in the environment
this work was done in. This is stated plainly, not glossed over: the
test exists, is real, is safe to run, and is ready to run — but
`docs/production-readiness.md` and the Phase 17 final report do not
claim a live run was actually observed. Whoever runs this with a real
key first should note the actual output here or in that report.

## Troubleshooting

- **`ImportError: AnthropicProvider requires the 'anthropic' package`**
  — `pip install anthropic` first; this is a real, correct failure, not
  a bug in the test.
- **`AuthenticationError`** — the API key is invalid, expired, or
  malformed. Double-check `ANTHROPIC_API_KEY` and that it hasn't been
  accidentally quoted or has trailing whitespace.
- **Test skips even with both variables set** — confirm
  `LIVE_TEST_MODE` is exactly `1`, `true`, or `True` (case-sensitive
  match against these three, per `test_live_anthropic_integration.py`)
  and `ANTHROPIC_API_KEY` is non-empty in the *same* shell/process
  running `python -m unittest`.
