"""Real RobotSafetyController tests. No physical robot is needed to
test this module's actual job: real enforced timeouts (genuine
threading.Thread.join(timeout=...) against a real slow fake driver),
a real emergency-stop latch, real fail-safe triggering, real state
verification, and a real audit trail. Every test here exercises real
logic, not a simulation of what the logic would do.
"""

import time
import unittest

from avishkar_layla.robotics.controller import RobotSafetyController
from avishkar_layla.robotics.errors import RobotActionFailedError, RobotActionTimeoutError, RobotEmergencyStoppedError


class FakeAudit:
    def __init__(self):
        self.records = []

    def record(self, event_type, payload, *, task_id=None, principal_id=None):
        self.records.append((event_type, payload))


class NormalDriver:
    def __init__(self):
        self.calls = []

    def execute(self, action, parameters):
        self.calls.append((action, dict(parameters)))
        return "ok"

    def get_state(self):
        return {"position": "home"}

    def emergency_stop(self):
        self.calls.append(("emergency_stop", {}))


class SlowDriver:
    def __init__(self, sleep_seconds):
        self._sleep_seconds = sleep_seconds

    def execute(self, action, parameters):
        time.sleep(self._sleep_seconds)
        return "too late"

    def get_state(self):
        return {}

    def emergency_stop(self):
        pass


class RaisingDriver:
    def execute(self, action, parameters):
        raise RuntimeError("motor fault")

    def get_state(self):
        return {"fault": True}

    def emergency_stop(self):
        pass


class BrokenEmergencyStopDriver:
    def execute(self, action, parameters):
        return "ok"

    def get_state(self):
        return {}

    def emergency_stop(self):
        raise RuntimeError("hardware link down")


class TestRobotSafetyControllerHappyPath(unittest.TestCase):
    def test_successful_action_returns_result_and_real_state(self):
        driver = NormalDriver()
        audit = FakeAudit()
        controller = RobotSafetyController(driver, audit=audit)

        result = controller("move_to", {"x": 1, "y": 2})

        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["state"], {"position": "home"})
        self.assertEqual(driver.calls, [("move_to", {"x": 1, "y": 2})])

    def test_action_completion_is_audited(self):
        driver = NormalDriver()
        audit = FakeAudit()
        controller = RobotSafetyController(driver, audit=audit)
        controller("move_to", {"x": 1})
        event_types = [e for e, _ in audit.records]
        self.assertIn("layla.robotics.action_completed", event_types)


class TestRobotSafetyControllerTimeout(unittest.TestCase):
    def test_real_timeout_raises_and_never_returns_the_late_result(self):
        driver = SlowDriver(sleep_seconds=2.0)
        controller = RobotSafetyController(driver, action_timeout_seconds=0.2)

        with self.assertRaises(RobotActionTimeoutError):
            controller("move_forever", {})

    def test_timeout_triggers_fail_safe_and_latches_emergency_stop(self):
        driver = SlowDriver(sleep_seconds=2.0)
        fail_safe_calls = []
        controller = RobotSafetyController(
            driver, action_timeout_seconds=0.2, fail_safe_callback=fail_safe_calls.append,
        )

        with self.assertRaises(RobotActionTimeoutError):
            controller("move_forever", {})

        self.assertEqual(len(fail_safe_calls), 1)
        self.assertTrue(controller.is_emergency_stopped)

    def test_after_a_timeout_further_actions_are_refused_until_reset(self):
        driver = SlowDriver(sleep_seconds=2.0)
        controller = RobotSafetyController(driver, action_timeout_seconds=0.2)
        with self.assertRaises(RobotActionTimeoutError):
            controller("move_forever", {})

        with self.assertRaises(RobotEmergencyStoppedError):
            controller("move_to", {"x": 1})


class TestRobotSafetyControllerDriverFailure(unittest.TestCase):
    def test_driver_exception_is_wrapped_and_triggers_fail_safe(self):
        driver = RaisingDriver()
        fail_safe_calls = []
        controller = RobotSafetyController(driver, fail_safe_callback=fail_safe_calls.append)

        with self.assertRaises(RobotActionFailedError):
            controller("move_to", {"x": 1})

        self.assertEqual(len(fail_safe_calls), 1)
        self.assertTrue(controller.is_emergency_stopped)

    def test_original_exception_is_preserved_as_the_cause(self):
        driver = RaisingDriver()
        controller = RobotSafetyController(driver)
        with self.assertRaises(RobotActionFailedError) as ctx:
            controller("move_to", {"x": 1})
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)


class TestRobotSafetyControllerEmergencyStop(unittest.TestCase):
    def test_emergency_stop_refuses_further_actions_immediately(self):
        driver = NormalDriver()
        controller = RobotSafetyController(driver)
        controller.emergency_stop(reason="operator request")

        with self.assertRaises(RobotEmergencyStoppedError):
            controller("move_to", {"x": 1})
        self.assertEqual(driver.calls, [("emergency_stop", {})])

    def test_emergency_stop_is_recorded_with_its_real_reason(self):
        driver = NormalDriver()
        audit = FakeAudit()
        controller = RobotSafetyController(driver, audit=audit)
        controller.emergency_stop(reason="obstacle detected")

        matching = [p for e, p in audit.records if e == "layla.robotics.emergency_stop"]
        self.assertEqual(matching, [{"reason": "obstacle detected"}])

    def test_reset_requires_an_explicit_authorized_by_and_is_audited(self):
        driver = NormalDriver()
        audit = FakeAudit()
        controller = RobotSafetyController(driver, audit=audit)
        controller.emergency_stop(reason="test")
        controller.reset_emergency_stop(authorized_by="operator-42")

        self.assertFalse(controller.is_emergency_stopped)
        result = controller("move_to", {"x": 1})
        self.assertEqual(result["result"], "ok")

        matching = [p for e, p in audit.records if e == "layla.robotics.emergency_stop_reset"]
        self.assertEqual(matching, [{"authorized_by": "operator-42"}])

    def test_a_broken_driver_emergency_stop_call_does_not_prevent_the_latch(self):
        """The software latch must engage even if the real hardware
        call fails -- human override can never be silently swallowed
        by a broken driver.
        """
        driver = BrokenEmergencyStopDriver()
        audit = FakeAudit()
        controller = RobotSafetyController(driver, audit=audit)

        controller.emergency_stop(reason="operator request")

        self.assertTrue(controller.is_emergency_stopped)
        error_events = [e for e, _ in audit.records if e == "layla.robotics.emergency_stop_driver_error"]
        self.assertEqual(len(error_events), 1)


if __name__ == "__main__":
    unittest.main()
