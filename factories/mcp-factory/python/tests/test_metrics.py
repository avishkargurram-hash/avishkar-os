import unittest

from avishkar_integration import MetricsCollector


class TestMetricsCollector(unittest.TestCase):
    def test_counts_calls(self):
        metrics = MetricsCollector()
        metrics.record("mcp:t", status="success", latency_ms=10.0)
        metrics.record("mcp:t", status="success", latency_ms=20.0)

        self.assertEqual(metrics.call_count("mcp:t"), 2)

    def test_tracks_errors(self):
        metrics = MetricsCollector()
        metrics.record("mcp:t", status="success", latency_ms=10.0)
        metrics.record("mcp:t", status="error", latency_ms=10.0)

        self.assertEqual(metrics.error_count("mcp:t"), 1)
        self.assertAlmostEqual(metrics.error_rate("mcp:t"), 0.5)

    def test_average_latency(self):
        metrics = MetricsCollector()
        metrics.record("mcp:t", status="success", latency_ms=10.0)
        metrics.record("mcp:t", status="success", latency_ms=20.0)

        self.assertAlmostEqual(metrics.average_latency_ms("mcp:t"), 15.0)

    def test_cost_defaults_to_zero_and_accumulates(self):
        metrics = MetricsCollector()
        metrics.record("mcp:t", status="success", latency_ms=1.0)
        metrics.record("mcp:t", status="success", latency_ms=1.0, cost=0.02)

        self.assertAlmostEqual(metrics.total_cost("mcp:t"), 0.02)

    def test_total_cost_without_key_sums_everything(self):
        metrics = MetricsCollector()
        metrics.record("mcp:a", status="success", latency_ms=1.0, cost=0.01)
        metrics.record("rest:b", status="success", latency_ms=1.0, cost=0.02)

        self.assertAlmostEqual(metrics.total_cost(), 0.03)

    def test_unknown_key_returns_zero_defaults(self):
        metrics = MetricsCollector()
        self.assertEqual(metrics.call_count("nonexistent"), 0)
        self.assertEqual(metrics.error_rate("nonexistent"), 0.0)
        self.assertEqual(metrics.average_latency_ms("nonexistent"), 0.0)


if __name__ == "__main__":
    unittest.main()
