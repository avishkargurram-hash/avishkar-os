"""End-to-end integration: real EmbodimentController (structural risk/
approval gate, ADR-0027) + real executors (ADR-0030) registered for
EMBODIMENT_BROWSER / EMBODIMENT_COMPUTER_CONTROL. Proves the full
chain Directive D Part III requires: risk classification -> approval
-> only then a real action -- and that a denied request never reaches
the real executor at all.
"""

import shutil
import tempfile
import unittest

from avishkar_agent import ApprovalGate

from avishkar_layla.approval import ApprovalManager
from avishkar_layla.embodiment import EMBODIMENT_BROWSER, EMBODIMENT_COMPUTER_CONTROL, EmbodimentController
from avishkar_layla.executors.browser_executor import BrowserExecutor
from avishkar_layla.executors.computer_control_executor import ComputerControlExecutor


class TestRealBrowserExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.browser = BrowserExecutor(headless=True)

    def tearDown(self):
        self.browser.close()

    def test_approved_navigate_actually_drives_a_real_browser(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "navigate", {"url": "data:text/html,<h1 id=t>real</h1>"}, task_id="t1",
        )

        self.assertEqual(result.status, "completed")
        self.assertIn("data:", result.output["url"])
        text = controller.request(EMBODIMENT_BROWSER, "get_text", {"selector": "#t"}, task_id="t1")
        self.assertEqual(text.output["text"], "real")

    def test_low_risk_browser_navigation_does_not_require_approval(self):
        """EMBODIMENT_BROWSER is NOT in embodiment.py's
        _DEFAULT_HIGH_RISK_CAPABILITIES -- plain navigation classifies
        LOW via the real text classifier and completes without ever
        consulting the (denying) gate. This is existing, deliberate
        ADR-0027 behavior, not a gap this test introduces.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "navigate", {"url": "data:text/html,<h1>ok to load</h1>"}, task_id="t1",
        )
        self.assertEqual(result.status, "completed")

    def test_denied_high_risk_browser_action_never_reaches_the_real_browser(self):
        """A genuinely dangerous-sounding browser action (matching
        classify_risk()'s real HIGH patterns) IS gated, and denial
        means the real executor is never touched at all.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_BROWSER, self.browser)

        result = controller.request(
            EMBODIMENT_BROWSER, "click", {"selector": "#submit", "action": "wire transfer payment"}, task_id="t1",
        )

        self.assertEqual(result.status, "denied")
        # Structural proof the real browser was never touched: no page
        # was ever created, so _page is still None.
        self.assertIsNone(self.browser._page)


class TestRealComputerControlExecutorThroughEmbodimentController(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="avishkar-layla-test-")
        self.executor = ComputerControlExecutor(workspace_root=self.workspace, allowed_shell_commands=("python",))

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_approved_shell_command_actually_runs(self):
        gate = ApprovalGate(policy="always_allow")
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        result = controller.request(
            EMBODIMENT_COMPUTER_CONTROL, "run_shell", {"command": "python -c \"print('ran for real')\""},
            task_id="t1",
        )

        self.assertEqual(result.status, "completed")
        self.assertIn("ran for real", result.output["stdout"])

    def test_denied_file_write_never_touches_the_real_filesystem(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        result = controller.request(
            EMBODIMENT_COMPUTER_CONTROL, "write_file", {"path": "should_not_exist.txt", "content": "x"},
            task_id="t1",
        )

        self.assertEqual(result.status, "denied")
        import os

        self.assertFalse(os.path.exists(os.path.join(self.workspace, "should_not_exist.txt")))

    def test_computer_control_is_always_high_risk_even_for_an_innocuous_looking_action(self):
        """embodiment.py's _DEFAULT_HIGH_RISK_CAPABILITIES forces
        EMBODIMENT_COMPUTER_CONTROL to RISK_HIGH regardless of text --
        even a request that reads as harmless still requires approval.
        """
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        controller = EmbodimentController(approval_manager=ApprovalManager(approval_gate=gate))
        controller.register_executor(EMBODIMENT_COMPUTER_CONTROL, self.executor)

        from avishkar_layla.types import RISK_HIGH

        result = controller.request(EMBODIMENT_COMPUTER_CONTROL, "list_dir", {"path": "."}, task_id="t1")
        self.assertEqual(result.risk_level, RISK_HIGH)
        self.assertEqual(result.status, "denied")


if __name__ == "__main__":
    unittest.main()
