import unittest

from avishkar_core import EventBus
from avishkar_router import (
    CompletionRequest,
    DuplicateModelError,
    Message,
    MockProvider,
    ModelSpec,
    NoAvailableProviderError,
    NoMatchingModelError,
    RoutingPolicy,
    RoutingRule,
    Router,
)


def _spec(model_id: str, provider: str = "mock", **overrides) -> ModelSpec:
    defaults = dict(
        capabilities=("chat",),
        input_cost_per_mtok=1.0,
        output_cost_per_mtok=2.0,
        max_context_tokens=1000,
        max_output_tokens=100,
    )
    defaults.update(overrides)
    return ModelSpec(model_id=model_id, provider=provider, **defaults)


def _req(**kwargs) -> CompletionRequest:
    kwargs.setdefault("messages", (Message(role="user", content="one two three"),))
    return CompletionRequest(**kwargs)


class TestRouterConstruction(unittest.TestCase):
    def test_duplicate_model_id_across_providers_raises(self):
        provider_a = MockProvider(models=(_spec("shared-model"),))
        provider_b = MockProvider(models=(_spec("shared-model"),))
        with self.assertRaises(DuplicateModelError):
            Router([provider_a, provider_b], RoutingPolicy(default_model="shared-model"))

    def test_list_models_aggregates_across_providers(self):
        provider_a = MockProvider(models=(_spec("model-a"),))
        provider_b = MockProvider(models=(_spec("model-b"),))
        router = Router([provider_a, provider_b], RoutingPolicy(default_model="model-a"))
        model_ids = {spec.model_id for spec in router.list_models()}
        self.assertEqual(model_ids, {"model-a", "model-b"})


class TestRouterRouting(unittest.TestCase):
    def test_routes_to_default_model(self):
        provider = MockProvider(models=(_spec("only-model"),), response_text="hi")
        router = Router([provider], RoutingPolicy(default_model="only-model"))

        response = router.route(_req())

        self.assertEqual(response.model_used, "only-model")
        self.assertEqual(response.provider_used, "mock")
        self.assertEqual(response.content, "hi")
        self.assertGreaterEqual(response.latency_ms, 0)

    def test_computes_cost_from_model_spec_pricing(self):
        provider = MockProvider(
            models=(_spec("priced-model", input_cost_per_mtok=10.0, output_cost_per_mtok=20.0),),
            response_text="a b",  # 2 output "tokens" per MockProvider's word-count stand-in
        )
        router = Router([provider], RoutingPolicy(default_model="priced-model"))

        response = router.route(_req(messages=(Message(role="user", content="x y z w"),)))

        # 4 input tokens * $10/1e6 + 2 output tokens * $20/1e6
        expected_cost = (4 / 1_000_000) * 10.0 + (2 / 1_000_000) * 20.0
        self.assertAlmostEqual(response.cost_usd, expected_cost)

    def test_explicit_model_override_is_used(self):
        provider = MockProvider(models=(_spec("model-a"), _spec("model-b")))
        router = Router([provider], RoutingPolicy(default_model="model-a"))

        response = router.route(_req(model="model-b"))

        self.assertEqual(response.model_used, "model-b")

    def test_no_matching_model_raises(self):
        provider = MockProvider(models=(_spec("model-a"),))
        router = Router([provider], RoutingPolicy(default_model="model-a"))

        with self.assertRaises(NoMatchingModelError):
            router.route(_req(model="nonexistent-model"))

    def test_rule_based_selection(self):
        provider = MockProvider(models=(_spec("cheap-model"), _spec("premium-model")))
        policy = RoutingPolicy(
            default_model="premium-model",
            rules=(RoutingRule(models=("cheap-model",), task_type="cheap"),),
        )
        router = Router([provider], policy)

        response = router.route(_req(task_type="cheap"))

        self.assertEqual(response.model_used, "cheap-model")


class TestRouterFallback(unittest.TestCase):
    def test_falls_back_to_next_candidate_on_provider_error(self):
        provider = MockProvider(
            models=(_spec("primary"), _spec("backup")),
            fail_models=("primary",),
        )
        policy = RoutingPolicy(
            default_model="primary",
            rules=(RoutingRule(models=("primary", "backup"), capabilities=()),),
        )
        router = Router([provider], policy)

        response = router.route(_req())

        self.assertEqual(response.model_used, "backup")

    def test_explicit_model_does_not_fall_back(self):
        # Explicit model = exactly one candidate, per CONTRACT.md SS3 --
        # even though a working backup model exists, an explicit request
        # for a failing model must not silently substitute another.
        provider = MockProvider(
            models=(_spec("primary"), _spec("backup")),
            fail_models=("primary",),
        )
        router = Router([provider], RoutingPolicy(default_model="backup"))

        with self.assertRaises(NoAvailableProviderError):
            router.route(_req(model="primary"))

    def test_all_candidates_failing_raises_no_available_provider(self):
        provider = MockProvider(
            models=(_spec("a"), _spec("b")),
            fail_models=("a", "b"),
        )
        policy = RoutingPolicy(default_model="a", rules=(RoutingRule(models=("a", "b")),))
        router = Router([provider], policy)

        with self.assertRaises(NoAvailableProviderError):
            router.route(_req())


class TestRouterCostTracking(unittest.TestCase):
    def test_cost_tracker_accumulates_by_caller(self):
        provider = MockProvider(models=(_spec("model-a", input_cost_per_mtok=1.0, output_cost_per_mtok=1.0),))
        router = Router([provider], RoutingPolicy(default_model="model-a"))

        router.route(_req(metadata={"caller": "agent-factory"}))
        router.route(_req(metadata={"caller": "agent-factory"}))
        router.route(_req(metadata={"caller": "workflow-factory"}))

        self.assertGreater(router.cost_tracker.total_cost_usd("agent-factory"), 0)
        self.assertGreater(router.cost_tracker.total_cost_usd(), 0)
        self.assertAlmostEqual(
            router.cost_tracker.total_cost_usd("agent-factory")
            + router.cost_tracker.total_cost_usd("workflow-factory"),
            router.cost_tracker.total_cost_usd(),
        )

    def test_cost_tracker_unknown_caller_returns_zero(self):
        provider = MockProvider(models=(_spec("model-a"),))
        router = Router([provider], RoutingPolicy(default_model="model-a"))
        router.route(_req())

        self.assertEqual(router.cost_tracker.total_cost_usd("nobody"), 0.0)


class TestRouterEventBusIntegration(unittest.TestCase):
    def test_publishes_completed_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("router.request.completed", lambda e: received.append(e))

        provider = MockProvider(models=(_spec("model-a"),))
        router = Router([provider], RoutingPolicy(default_model="model-a"), event_bus=bus)
        router.route(_req())

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["model"], "model-a")

    def test_publishes_fallback_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("router.fallback", lambda e: received.append(e))

        provider = MockProvider(models=(_spec("primary"), _spec("backup")), fail_models=("primary",))
        policy = RoutingPolicy(default_model="primary", rules=(RoutingRule(models=("primary", "backup")),))
        router = Router([provider], policy, event_bus=bus)
        router.route(_req())

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["model"], "primary")


if __name__ == "__main__":
    unittest.main()
