import unittest

from avishkar_layla import InvalidTransitionError, LaylaTask, StateMachine
from avishkar_layla.types import (
    APPROVAL_PENDING,
    COMPLETED,
    CONTEXT_LOADING,
    EXECUTING,
    FAILED,
    PLANNING,
    RECEIVED,
    SYNTHESIZING,
    UNDERSTANDING,
    VERIFYING,
)


class TestStateMachine(unittest.TestCase):
    def test_valid_transition_updates_state_and_history(self):
        task = LaylaTask(input="do the thing")
        sm = StateMachine()

        sm.transition(task, UNDERSTANDING)

        self.assertEqual(task.state, UNDERSTANDING)
        self.assertEqual(len(task.history), 1)
        self.assertEqual(task.history[0].from_state, RECEIVED)
        self.assertEqual(task.history[0].to_state, UNDERSTANDING)

    def test_invalid_transition_raises(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        with self.assertRaises(InvalidTransitionError):
            sm.transition(task, COMPLETED)  # RECEIVED can't jump straight to COMPLETED

    def test_full_happy_path(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        for state in (UNDERSTANDING, CONTEXT_LOADING, PLANNING, EXECUTING, VERIFYING, SYNTHESIZING, COMPLETED):
            sm.transition(task, state)
        self.assertEqual(task.state, COMPLETED)
        self.assertEqual(len(task.history), 7)

    def test_approval_pending_path(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        for state in (UNDERSTANDING, CONTEXT_LOADING, PLANNING, APPROVAL_PENDING, EXECUTING):
            sm.transition(task, state)
        self.assertEqual(task.state, EXECUTING)

    def test_exception_state_reachable_from_any_non_terminal_state(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        sm.transition(task, UNDERSTANDING)
        sm.transition(task, FAILED)
        self.assertEqual(task.state, FAILED)

    def test_no_transitions_out_of_terminal_state(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        sm.transition(task, UNDERSTANDING)
        sm.transition(task, FAILED)
        with self.assertRaises(InvalidTransitionError):
            sm.transition(task, EXECUTING)

    def test_is_terminal(self):
        task = LaylaTask(input="x")
        sm = StateMachine()
        self.assertFalse(sm.is_terminal(task))
        sm.transition(task, UNDERSTANDING)
        sm.transition(task, FAILED)
        self.assertTrue(sm.is_terminal(task))


if __name__ == "__main__":
    unittest.main()
