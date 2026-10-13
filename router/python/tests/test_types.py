import dataclasses
import unittest

from avishkar_router import CompletionRequest, Message, ModelSpec


class TestTypesAreFrozen(unittest.TestCase):
    def test_message_is_immutable(self):
        message = Message(role="user", content="hi")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            message.content = "changed"  # type: ignore[misc]

    def test_model_spec_is_immutable(self):
        spec = ModelSpec(
            model_id="m",
            provider="p",
            capabilities=("chat",),
            input_cost_per_mtok=1.0,
            output_cost_per_mtok=2.0,
            max_context_tokens=1000,
            max_output_tokens=100,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.model_id = "other"  # type: ignore[misc]

    def test_completion_request_defaults(self):
        request = CompletionRequest(messages=(Message(role="user", content="hi"),))
        self.assertIsNone(request.model)
        self.assertEqual(request.capabilities, ())
        self.assertIsNone(request.task_type)
        self.assertEqual(request.max_tokens, 1024)
        self.assertEqual(request.metadata, {})

    def test_completion_request_metadata_defaults_are_independent(self):
        # default_factory=dict must give each instance its own dict, not
        # a single mutable default shared across instances.
        a = CompletionRequest(messages=(Message(role="user", content="a"),))
        b = CompletionRequest(messages=(Message(role="user", content="b"),))
        self.assertIsNot(a.metadata, b.metadata)


if __name__ == "__main__":
    unittest.main()
