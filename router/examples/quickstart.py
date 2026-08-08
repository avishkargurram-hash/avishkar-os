"""AI Router Framework -- quickstart.

Demonstrates policy-based model selection, fallback on provider failure,
cost tracking per caller, and EventBus integration -- all using
MockProvider so this runs with no API key and no network call. Run it
directly:

    python router/examples/quickstart.py

No installation needed: this script adds core/python and router/python to
sys.path itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))

from avishkar_core import EventBus  # noqa: E402
from avishkar_router import (  # noqa: E402
    CompletionRequest,
    Message,
    MockProvider,
    ModelSpec,
    NoAvailableProviderError,
    RoutingPolicy,
    RoutingRule,
    Router,
)


def build_router(event_bus: EventBus) -> Router:
    # Two models on one MockProvider, priced differently -- a stand-in
    # for e.g. claude-opus-5 vs. claude-haiku-4-5. "flaky-model" is
    # configured to always fail, to demonstrate fallback.
    provider = MockProvider(
        models=(
            ModelSpec(
                model_id="premium-model",
                provider="mock",
                capabilities=("chat", "vision"),
                input_cost_per_mtok=5.0,
                output_cost_per_mtok=25.0,
                max_context_tokens=200_000,
                max_output_tokens=8_192,
            ),
            ModelSpec(
                model_id="cheap-model",
                provider="mock",
                capabilities=("chat",),
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=5.0,
                max_context_tokens=200_000,
                max_output_tokens=8_192,
            ),
            ModelSpec(
                model_id="flaky-model",
                provider="mock",
                capabilities=("chat",),
                input_cost_per_mtok=0.5,
                output_cost_per_mtok=2.5,
                max_context_tokens=200_000,
                max_output_tokens=8_192,
            ),
        ),
        response_text="This is a routed response.",
        fail_models=("flaky-model",),
    )

    policy = RoutingPolicy(
        default_model="premium-model",
        rules=(
            # Requests tagged task_type="cheap" prefer the cheap model,
            # falling back to premium if it's ever unavailable.
            RoutingRule(models=("cheap-model", "premium-model"), task_type="cheap"),
            # A request that first tries the flaky model demonstrates
            # fallback within a single rule.
            RoutingRule(models=("flaky-model", "premium-model"), task_type="demo-fallback"),
        ),
    )

    return Router([provider], policy, event_bus=event_bus)


def main() -> None:
    event_bus = EventBus()
    event_bus.subscribe(
        "router.fallback",
        lambda e: print(f"  [event] fallback: {e.payload['model']} -> next candidate"),
    )
    event_bus.subscribe(
        "router.request.completed",
        lambda e: print(f"  [event] completed via {e.payload['model']} (${e.payload['cost_usd']:.6f})"),
    )

    router = build_router(event_bus)

    request = CompletionRequest(
        messages=(Message(role="user", content="Summarize the Q3 roadmap."),),
        metadata={"caller": "workflow-factory"},
    )
    print("1. Default routing (no task_type / model override):")
    response = router.route(request)
    print(f"   -> model={response.model_used} cost=${response.cost_usd:.6f} content={response.content!r}\n")

    cheap_request = CompletionRequest(
        messages=(Message(role="user", content="Classify this ticket."),),
        task_type="cheap",
        metadata={"caller": "agent-factory"},
    )
    print("2. task_type='cheap' routes to the cheap model:")
    response = router.route(cheap_request)
    print(f"   -> model={response.model_used} cost=${response.cost_usd:.6f}\n")

    fallback_request = CompletionRequest(
        messages=(Message(role="user", content="Try the flaky model first."),),
        task_type="demo-fallback",
        metadata={"caller": "agent-factory"},
    )
    print("3. task_type='demo-fallback' -- flaky-model fails, router falls back:")
    response = router.route(fallback_request)
    print(f"   -> model={response.model_used} cost=${response.cost_usd:.6f}\n")

    print("4. Explicit model override skips policy entirely -- no fallback on failure:")
    explicit_request = CompletionRequest(
        messages=(Message(role="user", content="Force the flaky model."),),
        model="flaky-model",
    )
    try:
        router.route(explicit_request)
    except NoAvailableProviderError as exc:
        print(f"   -> raised as expected (explicit choice, no substitution): {exc}\n")

    print("5. Cost tracking by caller:")
    print(f"   workflow-factory spent: ${router.cost_tracker.total_cost_usd('workflow-factory'):.6f}")
    print(f"   agent-factory spent:    ${router.cost_tracker.total_cost_usd('agent-factory'):.6f}")
    print(f"   total across router:    ${router.cost_tracker.total_cost_usd():.6f}")


if __name__ == "__main__":
    main()
