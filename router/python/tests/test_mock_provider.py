import unittest

from avishkar_router import CompletionRequest, Message, MockProvider, ProviderUnavailableError


class TestMockProvider(unittest.TestCase):
    def test_list_models_returns_default_model(self):
        provider = MockProvider()
        models = provider.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].model_id, "mock-fast")
        self.assertEqual(models[0].provider, "mock")

    def test_complete_returns_configured_response(self):
        provider = MockProvider(response_text="hello there")
        request = CompletionRequest(messages=(Message(role="user", content="hi there"),))

        result = provider.complete(request, model_id="mock-fast")

        self.assertEqual(result.content, "hello there")
        self.assertEqual(result.output_tokens, 2)  # "hello there" -> 2 words
        self.assertEqual(result.input_tokens, 2)  # "hi there" -> 2 words
        self.assertEqual(result.stop_reason, "end_turn")

    def test_fail_models_raises_provider_error(self):
        provider = MockProvider(fail_models=("mock-fast",))
        request = CompletionRequest(messages=(Message(role="user", content="hi"),))

        with self.assertRaises(ProviderUnavailableError):
            provider.complete(request, model_id="mock-fast")


if __name__ == "__main__":
    unittest.main()
