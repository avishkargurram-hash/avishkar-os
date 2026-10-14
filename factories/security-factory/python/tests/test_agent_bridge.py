import unittest

from avishkar_agent import Task

from avishkar_security import (
    make_input_validation_guardrail,
    make_rate_limit_guardrail,
    make_secret_scanning_guardrail,
)


class TestSecretScanningGuardrail(unittest.TestCase):
    def test_blocks_task_containing_a_secret(self):
        guardrail = make_secret_scanning_guardrail()
        reason = guardrail.check(Task(input="here is my key AKIAIOSFODNN7EXAMPLE"))
        self.assertIsNotNone(reason)
        self.assertIn("aws_access_key_id", reason)

    def test_allows_ordinary_task(self):
        guardrail = make_secret_scanning_guardrail()
        self.assertIsNone(guardrail.check(Task(input="What's our deploy policy?")))


class TestRateLimitGuardrail(unittest.TestCase):
    def test_allows_calls_under_the_limit(self):
        clock = iter([0.0, 1.0, 2.0]).__next__
        guardrail = make_rate_limit_guardrail("rl", max_calls=3, window_seconds=10, clock=clock)

        for _ in range(3):
            self.assertIsNone(guardrail.check(Task(input="x")))

    def test_blocks_calls_over_the_limit_within_the_window(self):
        times = iter([0.0, 1.0, 2.0])
        guardrail = make_rate_limit_guardrail("rl", max_calls=2, window_seconds=10, clock=lambda: next(times))

        self.assertIsNone(guardrail.check(Task(input="x")))
        self.assertIsNone(guardrail.check(Task(input="x")))
        self.assertIsNotNone(guardrail.check(Task(input="x")))

    def test_old_calls_outside_the_window_are_forgotten(self):
        times = iter([0.0, 100.0])  # far apart -- outside a 10s window
        guardrail = make_rate_limit_guardrail("rl", max_calls=1, window_seconds=10, clock=lambda: next(times))

        self.assertIsNone(guardrail.check(Task(input="x")))
        self.assertIsNone(guardrail.check(Task(input="x")))  # allowed again -- old call expired


class TestInputValidationGuardrail(unittest.TestCase):
    def test_wraps_a_validator_function(self):
        def validator(text: str):
            return None if len(text) <= 10 else "too long"

        guardrail = make_input_validation_guardrail("length-check", validator)

        self.assertIsNone(guardrail.check(Task(input="short")))
        self.assertEqual(guardrail.check(Task(input="this is way too long")), "too long")


if __name__ == "__main__":
    unittest.main()
