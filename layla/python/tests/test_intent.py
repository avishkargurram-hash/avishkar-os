import unittest

from avishkar_layla.intent import IntentInterpreter


class TestIntentInterpreter(unittest.TestCase):
    def setUp(self):
        self.interpreter = IntentInterpreter()

    def test_question(self):
        intent = self.interpreter.interpret("What's the status of the project?")
        self.assertEqual(intent.category, "question")
        self.assertFalse(intent.requires_action)

    def test_command(self):
        intent = self.interpreter.interpret("Deploy the new release now")
        self.assertEqual(intent.category, "command")
        self.assertTrue(intent.requires_action)

    def test_request(self):
        intent = self.interpreter.interpret("Could you build a summary of the research")
        self.assertIn(intent.category, ("request", "question"))

    def test_urgent_detected(self):
        intent = self.interpreter.interpret("This is urgent, please respond immediately")
        self.assertEqual(intent.urgency, "urgent")

    def test_information_default(self):
        intent = self.interpreter.interpret("The sky is blue today in general.")
        self.assertEqual(intent.category, "information")
        self.assertFalse(intent.requires_action)


if __name__ == "__main__":
    unittest.main()
