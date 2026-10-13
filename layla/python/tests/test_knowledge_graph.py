import tempfile
import unittest
from pathlib import Path

from avishkar_agent import InMemoryMemoryPolicy
from avishkar_memory import FileMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.knowledge_graph import LaylaKnowledgeGraph, NodeNotFoundError


def _graph():
    return LaylaKnowledgeGraph(LaylaMemoryPolicy(InMemoryMemoryPolicy()), clock=lambda: 0.0)


class TestKnowledgeGraphNodes(unittest.TestCase):
    def test_add_and_get_node(self):
        graph = _graph()
        graph.add_node("project-1", "project", "Mission Layla")

        node = graph.get_node("project-1")
        self.assertEqual(node.label, "Mission Layla")
        self.assertEqual(node.node_type, "project")

    def test_get_missing_node_returns_none(self):
        self.assertIsNone(_graph().get_node("nope"))

    def test_query_by_type(self):
        graph = _graph()
        graph.add_node("p1", "project", "A")
        graph.add_node("p2", "project", "B")
        graph.add_node("g1", "goal", "C")

        projects = graph.query_by_type("project")
        self.assertEqual({n.id for n in projects}, {"p1", "p2"})

    def test_re_adding_a_node_preserves_created_at(self):
        graph = _graph()
        first = graph.add_node("p1", "project", "A")
        second = graph.add_node("p1", "project", "A renamed")

        self.assertEqual(first.created_at, second.created_at)
        self.assertEqual(second.label, "A renamed")


class TestKnowledgeGraphEdges(unittest.TestCase):
    def test_add_edge_requires_both_nodes_to_exist(self):
        graph = _graph()
        graph.add_node("p1", "project", "A")
        with self.assertRaises(NodeNotFoundError):
            graph.add_edge("e1", "p1", "does-not-exist", "depends_on")

    def test_add_edge_between_real_nodes_succeeds(self):
        graph = _graph()
        graph.add_node("p1", "project", "A")
        graph.add_node("g1", "goal", "B")

        edge = graph.add_edge("e1", "p1", "g1", "has_goal")

        self.assertEqual(edge.source_id, "p1")
        self.assertEqual(edge.target_id, "g1")

    def test_neighbors_finds_edges_in_either_direction(self):
        graph = _graph()
        graph.add_node("a", "x", "A")
        graph.add_node("b", "x", "B")
        graph.add_edge("e1", "a", "b", "related_to")

        self.assertEqual(len(graph.neighbors("a")), 1)
        self.assertEqual(len(graph.neighbors("b")), 1)


class TestKnowledgeGraphTraversal(unittest.TestCase):
    def _chain_graph(self):
        graph = _graph()
        for node_id in ("a", "b", "c", "d"):
            graph.add_node(node_id, "x", node_id)
        graph.add_edge("e1", "a", "b", "next")
        graph.add_edge("e2", "b", "c", "next")
        graph.add_edge("e3", "c", "d", "next")
        return graph

    def test_bfs_computes_real_depths(self):
        graph = self._chain_graph()

        depths = graph.bfs("a", max_depth=10)

        self.assertEqual(depths, {"a": 0, "b": 1, "c": 2, "d": 3})

    def test_bfs_respects_max_depth(self):
        graph = self._chain_graph()

        depths = graph.bfs("a", max_depth=1)

        self.assertEqual(depths, {"a": 0, "b": 1})

    def test_bfs_on_missing_start_returns_empty(self):
        self.assertEqual(_graph().bfs("nope"), {})

    def test_shortest_path_real_bfs(self):
        graph = self._chain_graph()

        path = graph.shortest_path("a", "d")

        self.assertEqual(path, ("a", "b", "c", "d"))

    def test_shortest_path_same_node(self):
        graph = self._chain_graph()
        self.assertEqual(graph.shortest_path("a", "a"), ("a",))

    def test_shortest_path_no_connection_returns_none(self):
        graph = _graph()
        graph.add_node("a", "x", "A")
        graph.add_node("b", "x", "B")

        self.assertIsNone(graph.shortest_path("a", "b"))

    def test_shortest_path_missing_node_returns_none(self):
        graph = self._chain_graph()
        self.assertIsNone(graph.shortest_path("a", "nope"))


class TestKnowledgeGraphCrossInstancePersistence(unittest.TestCase):
    def test_nodes_and_edges_survive_a_simulated_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            first = LaylaKnowledgeGraph(memory, clock=lambda: 0.0)
            first.add_node("a", "x", "A")
            first.add_node("b", "x", "B")
            first.add_edge("e1", "a", "b", "related_to")

            second = LaylaKnowledgeGraph(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))), clock=lambda: 0.0)

            self.assertIsNotNone(second.get_node("a"))
            self.assertEqual(second.shortest_path("a", "b"), ("a", "b"))


if __name__ == "__main__":
    unittest.main()
