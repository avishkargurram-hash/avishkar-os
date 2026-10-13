import unittest

from avishkar_agent import InMemoryMemoryPolicy
from avishkar_knowledge import KnowledgeBase

from avishkar_layla import LaylaMemoryPolicy, LaylaTask
from avishkar_layla.context import ContextBuilder


class TestContextBuilder(unittest.TestCase):
    def test_pulls_requested_memories(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        memory.remember("semantic", "preferred-tone", "concise")
        task = LaylaTask(input="draft an update")

        context = ContextBuilder().build(task, memory, memory_lookups=[("semantic", "preferred-tone")])

        self.assertEqual(context["memories"]["semantic:preferred-tone"], "concise")

    def test_missing_memory_is_silently_skipped(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        task = LaylaTask(input="draft an update")

        context = ContextBuilder().build(task, memory, memory_lookups=[("semantic", "does-not-exist")])

        self.assertEqual(context["memories"], {})

    def test_pulls_knowledge_search_results(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        kb = KnowledgeBase()
        kb.ingest("policy", "All deploys require a passing test suite and review.")
        task = LaylaTask(input="what do we require before deploying")

        context = ContextBuilder().build(task, memory, knowledge_bases=[kb])

        self.assertTrue(context["knowledge"])
        self.assertEqual(context["knowledge"][0].chunk.document_id, "policy")

    def test_task_input_always_present(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        task = LaylaTask(input="hello")
        context = ContextBuilder().build(task, memory)
        self.assertEqual(context["task_input"], "hello")


if __name__ == "__main__":
    unittest.main()
