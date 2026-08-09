import tempfile
import unittest
from pathlib import Path

from avishkar_memory import FileMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy, LaylaTask, StateMachine
from avishkar_layla.session import SessionManager
from avishkar_layla.types import COMPLETED, UNDERSTANDING


class TestSessionManagerInMemory(unittest.TestCase):
    def test_save_and_load_round_trips(self):
        from avishkar_agent import InMemoryMemoryPolicy

        manager = SessionManager(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        task = LaylaTask(input="do the thing")
        StateMachine().transition(task, UNDERSTANDING)

        manager.save(task)
        loaded = manager.load(task.id)

        self.assertEqual(loaded.id, task.id)
        self.assertEqual(loaded.state, UNDERSTANDING)
        self.assertEqual(len(loaded.history), 1)

    def test_list_incomplete_excludes_terminal_tasks(self):
        from avishkar_agent import InMemoryMemoryPolicy

        manager = SessionManager(LaylaMemoryPolicy(InMemoryMemoryPolicy()))
        sm = StateMachine()

        in_progress = LaylaTask(input="a")
        sm.transition(in_progress, UNDERSTANDING)
        manager.save(in_progress)

        done = LaylaTask(input="b")
        sm.transition(done, UNDERSTANDING)
        # fast-path directly for the test's purposes -- exercise the
        # real transition table rather than hand-setting .state.
        for state in ("CONTEXT_LOADING", "PLANNING", "EXECUTING", "VERIFYING", "SYNTHESIZING", COMPLETED):
            sm.transition(done, state)
        manager.save(done)

        incomplete = manager.list_incomplete()

        self.assertEqual({t.id for t in incomplete}, {in_progress.id})


class TestSessionManagerCrossInstanceRestartRecovery(unittest.TestCase):
    """The load-bearing proof: a process restart followed by a fresh
    SessionManager instance against the same backing store recovers
    every incomplete task -- the same cross-instance persistence proof
    legal-compliance/education-knowledge already established for their
    own FileMemoryPolicy usage (Phase 13).
    """

    def test_incomplete_task_survives_a_simulated_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_process = SessionManager(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))))
            task = LaylaTask(input="research competitor funding rounds")
            StateMachine().transition(task, UNDERSTANDING)
            first_process.save(task)

            # Simulate a restart: a brand-new SessionManager, brand-new
            # FileMemoryPolicy instance, same root_dir -- no shared
            # Python object between "before" and "after".
            second_process = SessionManager(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))))
            recovered = second_process.list_incomplete()

            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].id, task.id)
            self.assertEqual(recovered[0].state, UNDERSTANDING)


if __name__ == "__main__":
    unittest.main()
