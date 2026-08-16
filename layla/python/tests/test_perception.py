import unittest

from avishkar_layla.perception import (
    PERCEPTION_VISION,
    PERCEPTION_VOICE,
    PerceptionEngine,
    PerceptionObservation,
    PerceptionSourceNotConfiguredError,
    UnknownPerceptionSourceError,
)


class TestPerceptionEngineUnconfigured(unittest.TestCase):
    def test_observe_unconfigured_source_raises_documented_boundary(self):
        engine = PerceptionEngine()
        with self.assertRaises(PerceptionSourceNotConfiguredError) as ctx:
            engine.observe(PERCEPTION_VOICE)
        self.assertIn("ADAPTER READY", str(ctx.exception))

    def test_unknown_source_raises(self):
        engine = PerceptionEngine()
        with self.assertRaises(UnknownPerceptionSourceError):
            engine.observe("not-a-real-source")

    def test_register_unknown_source_raises(self):
        engine = PerceptionEngine()
        with self.assertRaises(UnknownPerceptionSourceError):
            engine.register_capture("not-a-real-source", lambda: None)

    def test_observe_all_with_nothing_configured_is_empty(self):
        engine = PerceptionEngine()
        self.assertEqual(engine.observe_all(), ())


class TestPerceptionEngineWithFakeCapture(unittest.TestCase):
    def test_registered_capture_is_used(self):
        engine = PerceptionEngine()
        engine.register_capture(
            PERCEPTION_VISION,
            lambda: PerceptionObservation(
                source=PERCEPTION_VISION, observation_type="scene", content="empty room",
                confidence=0.8, permissions_required=("camera",),
            ),
        )

        observation = engine.observe(PERCEPTION_VISION)

        self.assertEqual(observation.content, "empty room")
        self.assertEqual(observation.confidence, 0.8)
        self.assertEqual(observation.permissions_required, ("camera",))

    def test_configured_sources_reports_only_registered_ones(self):
        engine = PerceptionEngine()
        engine.register_capture(PERCEPTION_VOICE, lambda: PerceptionObservation(source=PERCEPTION_VOICE, observation_type="x", content="y"))

        self.assertEqual(engine.configured_sources(), (PERCEPTION_VOICE,))

    def test_observe_all_only_calls_configured_captures(self):
        engine = PerceptionEngine()
        calls = []
        engine.register_capture(PERCEPTION_VOICE, lambda: calls.append(1) or PerceptionObservation(source=PERCEPTION_VOICE, observation_type="x", content="y"))

        results = engine.observe_all()

        self.assertEqual(len(results), 1)
        self.assertEqual(len(calls), 1)

    def test_observation_defaults_are_real_not_fabricated(self):
        observation = PerceptionObservation(source=PERCEPTION_VOICE, observation_type="transcript", content="hello")
        self.assertEqual(observation.confidence, 1.0)
        self.assertEqual(observation.retention_policy, "session")
        self.assertTrue(observation.timestamp)  # a real ISO timestamp was generated


if __name__ == "__main__":
    unittest.main()
