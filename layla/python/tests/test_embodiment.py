import unittest

from avishkar_agent import ApprovalGate

from avishkar_layla.approval import ApprovalManager
from avishkar_layla.embodiment import (
    EMBODIMENT_ADB,
    EMBODIMENT_BROWSER,
    EMBODIMENT_HOME_ASSISTANT,
    EMBODIMENT_MQTT,
    EmbodimentCapabilityNotConfiguredError,
    EmbodimentController,
    EmbodimentNotApprovedError,
    UnknownEmbodimentCapabilityError,
)
from avishkar_layla.types import RISK_HIGH


class TestEmbodimentControllerUnknownCapability(unittest.TestCase):
    def test_unknown_capability_on_request_raises(self):
        controller = EmbodimentController()
        with self.assertRaises(UnknownEmbodimentCapabilityError):
            controller.request("not-a-real-capability", "do-thing", {}, task_id="t1")

    def test_unknown_capability_on_register_raises(self):
        controller = EmbodimentController()
        with self.assertRaises(UnknownEmbodimentCapabilityError):
            controller.register_executor("not-a-real-capability", lambda action, params: None)


class TestEmbodimentControllerFailsClosed(unittest.TestCase):
    def test_high_risk_capability_with_no_approval_manager_fails_closed(self):
        controller = EmbodimentController()  # no approval_manager wired
        with self.assertRaises(EmbodimentNotApprovedError):
            controller.request(EMBODIMENT_ADB, "shell", {"command": "ls"}, task_id="t1")

    def test_high_risk_capability_denied_by_gate_returns_denied_not_an_exception(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        approval_manager = ApprovalManager(approval_gate=gate)
        controller = EmbodimentController(approval_manager=approval_manager)
        controller.register_executor(EMBODIMENT_ADB, lambda action, params: "should never run")

        result = controller.request(EMBODIMENT_ADB, "shell", {"command": "ls"}, task_id="t1")

        self.assertEqual(result.status, "denied")
        self.assertEqual(result.risk_level, RISK_HIGH)

    def test_capabilities_not_in_the_default_high_risk_set_still_get_real_risk_classification(self):
        """browser isn't in _DEFAULT_HIGH_RISK_CAPABILITIES, but a
        genuinely dangerous action description must still classify HIGH
        via the real classify_risk() text classifier.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        approval_manager = ApprovalManager(approval_gate=gate)
        controller = EmbodimentController(approval_manager=approval_manager)

        result = controller.request(
            EMBODIMENT_BROWSER, "submit_form", {"action": "wire transfer payment"}, task_id="t1",
        )

        self.assertEqual(result.status, "denied")  # a real dangerous-text match, not fabricated


class TestEmbodimentControllerApprovedButUnconfigured(unittest.TestCase):
    def test_approved_high_risk_request_with_no_executor_raises_adapter_ready(self):
        gate = ApprovalGate(policy="always_allow")
        approval_manager = ApprovalManager(approval_gate=gate)
        controller = EmbodimentController(approval_manager=approval_manager)

        with self.assertRaises(EmbodimentCapabilityNotConfiguredError) as ctx:
            controller.request(EMBODIMENT_HOME_ASSISTANT, "unlock_door", {"entity_id": "lock.front_door"}, task_id="t1")
        self.assertIn("ADAPTER READY", str(ctx.exception))


class TestEmbodimentControllerWithRealExecutor(unittest.TestCase):
    def test_approved_request_calls_the_real_executor(self):
        gate = ApprovalGate(policy="always_allow")
        approval_manager = ApprovalManager(approval_gate=gate)
        controller = EmbodimentController(approval_manager=approval_manager)
        calls = []
        controller.register_executor(EMBODIMENT_ADB, lambda action, params: calls.append((action, params)) or "ok")

        result = controller.request(EMBODIMENT_ADB, "tap", {"x": 10, "y": 20}, task_id="t1")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "ok")
        self.assertEqual(len(calls), 1)

    def test_configured_capabilities_reports_registered_ones(self):
        controller = EmbodimentController()
        controller.register_executor(EMBODIMENT_ADB, lambda action, params: None)
        self.assertEqual(controller.configured_capabilities(), (EMBODIMENT_ADB,))


class TestEmbodimentControllerMQTTIsHighRiskByDefault(unittest.TestCase):
    """Directive D Part VIII (ADR-0035): EMBODIMENT_MQTT was added to
    _DEFAULT_HIGH_RISK_CAPABILITIES because a real MQTT `publish` can
    command a real physical device -- the same reasoning already
    applied to EMBODIMENT_HOME_ASSISTANT/EMBODIMENT_ADB/
    EMBODIMENT_COMPUTER_CONTROL.
    """

    def test_mqtt_publish_requires_approval_even_for_innocuous_looking_text(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_MQTT, lambda action, params: "should never run")

        result = controller.request(EMBODIMENT_MQTT, "publish", {"topic": "home/sensor/status"}, task_id="t1")

        self.assertEqual(result.status, "denied")
        self.assertEqual(result.risk_level, RISK_HIGH)


if __name__ == "__main__":
    unittest.main()
