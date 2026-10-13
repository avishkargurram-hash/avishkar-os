"""Controlled live integration validation (Priority 17.5, ADR-0025).
See CONTRACT.md SS19 and docs/live-integration-guide.md.

**This test makes a real, billed network call to the live Anthropic
API when explicitly enabled.** It is SKIPPED by default -- every other
test in this platform (661+ before this priority) never makes a
network call, and this one file is a deliberate, narrow, opt-in
exception, not a change to that discipline.

To actually run it:

    LIVE_TEST_MODE=1 ANTHROPIC_API_KEY=sk-ant-... \
      PYTHONPATH="core/python;router/python;factories/agent-factory/python;factories/knowledge-factory/python;factories/mcp-factory/python;factories/memory-factory/python;factories/security-factory/python;layla/python" \
      python -m unittest layla.python.tests.test_live_anthropic_integration -v

Both `LIVE_TEST_MODE=1` and a real `ANTHROPIC_API_KEY` must be present
-- the credential is read from the environment only, never hardcoded,
never logged, never committed. Missing either: the test SKIPS (a
green, honest "not run," not a fabricated pass and not a failure).

Safety, by construction, not by convention:
- Fixed to `claude-haiku-4-5` -- the cheapest model in the catalog
  (router/python/avishkar_router/providers/anthropic_provider.py).
- `max_tokens=32` and a single, trivial, fixed prompt -- real spend for
  one run is a small fraction of a cent, and the test asserts on it
  (see `_MAX_ACCEPTABLE_COST_USD` below) rather than trusting that.
- The Layla task is phrased as a read-only, LOW-risk informational
  request. It never reaches DelegationEngine's write-classified path,
  never touches an approval gate, and never invokes any tool/channel
  adapter (email, MCP, REST) -- only a single Chief Domain Agent's own
  `handle()` call through a real Router to a real model.
- No email/message is sent, no record created/modified/deleted, no
  financial or destructive operation of any kind is performed anywhere
  in this test.
"""

from __future__ import annotations

import os
import unittest

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import Router, RoutingPolicy
from avishkar_router.providers.anthropic_provider import AnthropicProvider

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.types import COMPLETED

_LIVE_TEST_MODE = os.environ.get("LIVE_TEST_MODE") in ("1", "true", "True")
_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
_SKIP_REASON = (
    "Live Anthropic API test skipped -- set both LIVE_TEST_MODE=1 and a real "
    "ANTHROPIC_API_KEY to run it. See docs/live-integration-guide.md."
)

# A real request against real infrastructure is not free; this bounds
# what "went wrong" looks like versus "the test itself is broken" --
# claude-haiku-4-5 at $1.00/$5.00 per Mtok with max_tokens=32 and a
# ~20-token prompt should cost on the order of $0.0002. $0.01 is a
# generous, hand-picked ceiling: if a single call to this specific
# prompt ever costs more than that, something is wrong (wrong model
# selected, huge unexpected output) and the test should fail loudly
# rather than silently accept it.
_MAX_ACCEPTABLE_COST_USD = 0.01


@unittest.skipUnless(_LIVE_TEST_MODE and _API_KEY, _SKIP_REASON)
class TestLiveAnthropicIntegration(unittest.TestCase):
    """Validates the full path: Layla (ExecutiveRuntime) -> Planner ->
    DelegationEngine -> a real ChiefDomainAgent -> a real AI Router ->
    the real Anthropic API -> a real response -> ResultValidator ->
    ExecutiveSynthesizer. Every piece through Phase 16 is real except
    the model call itself in every OTHER test in this platform; here,
    that piece is real too.
    """

    def test_full_layla_pipeline_completes_a_real_model_call(self):
        provider = AnthropicProvider(api_key=_API_KEY)
        # Restrict to the cheapest model only -- RoutingPolicy would
        # otherwise consider every model AnthropicProvider publishes.
        cheap_models = tuple(m for m in provider.list_models() if m.model_id == "claude-haiku-4-5")
        self.assertTrue(cheap_models, "claude-haiku-4-5 must be in AnthropicProvider's catalog")
        provider = AnthropicProvider(api_key=_API_KEY, models=cheap_models)

        router = Router([provider], RoutingPolicy(default_model="claude-haiku-4-5"))

        blueprint = AgentBlueprint(
            name="diagnostics-agent", domain="System Diagnostics", version="0.1.0",
            mission="Answer a trivial diagnostic prompt to prove the live integration path works.",
            default_model="claude-haiku-4-5",
        )
        agent = ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)
        orchestrator = Orchestrator([agent])

        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        runtime = ExecutiveRuntime(
            orchestrator=orchestrator, agent_domains={"diagnostics-agent": "System Diagnostics"}, memory=memory,
        )

        # Deliberately trivial, read-only, LOW-risk: no financial/
        # legal/destructive/production-deploy keyword anywhere in this
        # sentence, and the agent's own max_tokens keeps output short
        # regardless of what the model tries to produce.
        task = runtime.handle_event(
            "Run a basic diagnostics check: reply with exactly the single word OK."
        )

        self.assertEqual(task.state, COMPLETED, f"task did not complete: {task.blocked_reason}")
        self.assertTrue(task.result, "expected a non-empty executive summary")

        delegation_events = [r for r in runtime.audit.history(task.id) if r.event_type == "layla.delegation.completed"]
        self.assertEqual(len(delegation_events), 1)
        cost_usd = delegation_events[0].payload.get("cost_usd", 0.0)

        # Router itself is the authoritative source for latency/tokens/
        # cost/request_id -- CostTracker + the returned CompletionResponse
        # (surfaced here via cost_tracker, since DelegationRecord/
        # AuditLogger only carry cost_usd, not the full response object).
        total_cost = router.cost_tracker.total_cost_usd()

        print("\n--- Live Anthropic integration result ---")
        print(f"  task.state:        {task.state}")
        print(f"  task.result:       {task.result!r}")
        print(f"  cost_usd (audit):  {cost_usd}")
        print(f"  cost_usd (router): {total_cost}")
        print("------------------------------------------")

        self.assertGreaterEqual(total_cost, 0.0)
        self.assertLessEqual(
            total_cost, _MAX_ACCEPTABLE_COST_USD,
            f"single-call cost ${total_cost} exceeded the ${_MAX_ACCEPTABLE_COST_USD} safety ceiling -- "
            f"stopping rather than silently accepting unexpected spend",
        )


if __name__ == "__main__":
    unittest.main()
