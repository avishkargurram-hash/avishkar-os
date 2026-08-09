import unittest

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from creative_media_agent import (
    _analyze_pacing,
    _count_words,
    _no_verbatim_copyrighted_reproduction,
    build_creative_media_agent,
    load_blueprint,
)


def _router(response_text: str = "Here's a draft to use as a starting point in your own voice.") -> Router:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=1.0, output_cost_per_mtok=1.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


class TestBlueprint(unittest.TestCase):
    def test_loads_committed_blueprint(self):
        blueprint = load_blueprint()
        self.assertEqual(blueprint.name, "creative-media")
        self.assertIn("story-editor", blueprint.sub_agent_roles)


class TestCountWordsTool(unittest.TestCase):
    def test_counts_words(self):
        self.assertEqual(_count_words("The quick brown fox jumps."), 5)

    def test_empty_string_is_zero(self):
        self.assertEqual(_count_words(""), 0)


class TestAnalyzePacingTool(unittest.TestCase):
    def test_single_sentence_is_unclear(self):
        self.assertEqual(_analyze_pacing("Hello there"), "unclear")

    def test_uniform_short_sentences_are_choppy(self):
        self.assertEqual(_analyze_pacing("I ran. I jumped. I fell."), "choppy")

    def test_long_sentences_are_dense(self):
        # 26 words -- deliberately well over the 20-word/sentence
        # threshold so this test isn't sensitive to off-by-a-few-word
        # miscounts.
        long_sentence = (
            "This is a very long and elaborately constructed sentence meant to run on "
            "and on with many extra clauses and details attached to make it longer."
        )
        self.assertEqual(_analyze_pacing(f"{long_sentence} {long_sentence}"), "dense")

    def test_varied_length_sentences_are_flowing(self):
        text = "I ran fast down the street chasing the bus while shouting for it to wait. It stopped."
        self.assertEqual(_analyze_pacing(text), "flowing")


class TestGuardrail(unittest.TestCase):
    def test_blocks_verbatim_reproduction_request(self):
        reason = _no_verbatim_copyrighted_reproduction(Task(input="Please reproduce the full text of this novel"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_verbatim_copyrighted_reproduction(Task(input="Help me draft an opening scene.")))


class TestAgentIntegration(unittest.TestCase):
    def test_normal_task_completes(self):
        agent = build_creative_media_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Help me draft an opening scene for my short story."))
        self.assertEqual(result.status, "completed")

    def test_verbatim_reproduction_request_is_blocked(self):
        agent = build_creative_media_agent(_router(), model_override="mock-fast")
        result = agent.handle(Task(input="Please reproduce the full text of this novel"))
        self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        agent = build_creative_media_agent(_router(), model_override="mock-fast")
        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:unsplash/search_stock_images", "sunset over mountains")

    def test_knowledge_search_tool_is_callable(self):
        agent = build_creative_media_agent(_router(), model_override="mock-fast")
        results = agent.tools.call("search_craft_references", "what is three-act structure")
        self.assertTrue(results)

    def test_sub_agent_routing_to_story_editor(self):
        agent = build_creative_media_agent(_router(), model_override="mock-fast")
        role = agent.route_to_sub_agent_role(Task(input="Can the story-editor review this?"))
        self.assertEqual(role, "story-editor")


if __name__ == "__main__":
    unittest.main()
