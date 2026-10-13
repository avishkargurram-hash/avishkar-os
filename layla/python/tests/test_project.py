import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy, Project
from avishkar_layla.project import ProjectStore


class TestProjectStore(unittest.TestCase):
    def test_save_and_load_round_trips(self):
        store = ProjectStore(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        project = Project(
            id="proj-1", name="Humanify Passport",
            objectives=("ship v1",), owners=("alice",), status="active",
        )

        store.save(project)
        loaded = store.load("proj-1")

        self.assertEqual(loaded, project)

    def test_load_unknown_id_returns_none(self):
        store = ProjectStore(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        self.assertIsNone(store.load("does-not-exist"))

    def test_list_ids_and_list_all(self):
        store = ProjectStore(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        store.save(Project(id="p1", name="A"))
        store.save(Project(id="p2", name="B"))

        self.assertEqual(set(store.list_ids()), {"p1", "p2"})
        self.assertEqual({p.name for p in store.list_all()}, {"A", "B"})

    def test_generic_no_hardcoded_products(self):
        # Any project name works -- nothing in ProjectStore special-cases
        # a specific product name.
        store = ProjectStore(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        store.save(Project(id="p1", name="A Completely Made Up Product"))
        self.assertEqual(store.load("p1").name, "A Completely Made Up Product")


if __name__ == "__main__":
    unittest.main()
