import unittest

from avishkar_workflow import (
    DuplicateStepError,
    MaxStepsExceededError,
    RetryPolicy,
    Step,
    StepExecutionError,
    UnknownStepError,
    WorkflowEngine,
    WorkflowSpec,
)


class TestWorkflowSpecValidation(unittest.TestCase):
    def test_duplicate_step_id_raises(self):
        with self.assertRaises(DuplicateStepError):
            WorkflowSpec(
                "wf",
                [Step("a", lambda s: {}), Step("a", lambda s: {})],
                start="a",
            )

    def test_unknown_start_raises(self):
        with self.assertRaises(UnknownStepError):
            WorkflowSpec("wf", [Step("a", lambda s: {})], start="does-not-exist")

    def test_unknown_next_target_raises(self):
        with self.assertRaises(UnknownStepError):
            WorkflowSpec(
                "wf",
                [Step("a", lambda s: {}, next="ghost")],
                start="a",
            )

    def test_valid_spec_constructs(self):
        spec = WorkflowSpec("wf", [Step("a", lambda s: {})], start="a")
        self.assertEqual(spec.start, "a")
        self.assertIn("a", spec.steps)


class TestWorkflowEngineLinear(unittest.TestCase):
    def test_runs_linear_chain_and_merges_state(self):
        steps = [
            Step("double", lambda s: {"x": s["x"] * 2}, next="increment"),
            Step("increment", lambda s: {"x": s["x"] + 1}, next=None),
        ]
        spec = WorkflowSpec("wf", steps, start="double")

        result = WorkflowEngine().run(spec, {"x": 5})

        self.assertEqual(result.state["x"], 11)
        self.assertEqual(result.history, ("double", "increment"))
        self.assertEqual(result.status, "completed")

    def test_single_step_workflow_ends_when_next_is_none(self):
        spec = WorkflowSpec("wf", [Step("only", lambda s: {"done": True})], start="only")
        result = WorkflowEngine().run(spec, {})
        self.assertEqual(result.history, ("only",))
        self.assertTrue(result.state["done"])


class TestWorkflowEngineBranching(unittest.TestCase):
    def test_branch_overrides_static_next(self):
        def choose(state):
            return "even" if state["n"] % 2 == 0 else "odd"

        steps = [
            Step("classify", lambda s: {}, next="odd", branch=choose),
            Step("even", lambda s: {"label": "even"}),
            Step("odd", lambda s: {"label": "odd"}),
        ]
        spec = WorkflowSpec("wf", steps, start="classify")

        result = WorkflowEngine().run(spec, {"n": 4})

        self.assertEqual(result.state["label"], "even")
        self.assertEqual(result.history, ("classify", "even"))

    def test_branch_returning_none_ends_workflow(self):
        steps = [Step("start", lambda s: {}, branch=lambda s: None)]
        spec = WorkflowSpec("wf", steps, start="start")

        result = WorkflowEngine().run(spec, {})

        self.assertEqual(result.history, ("start",))

    def test_branch_to_unknown_step_raises_at_runtime(self):
        steps = [Step("start", lambda s: {}, branch=lambda s: "ghost")]
        spec = WorkflowSpec("wf", steps, start="start")

        with self.assertRaises(UnknownStepError):
            WorkflowEngine().run(spec, {})


class TestWorkflowEngineRetry(unittest.TestCase):
    def test_step_retries_then_succeeds(self):
        attempts = []

        def flaky(state):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("not yet")
            return {"ok": True}

        sleeps = []
        spec = WorkflowSpec(
            "wf",
            [Step("flaky", flaky, retry_policy=RetryPolicy(max_attempts=3))],
            start="flaky",
        )

        result = WorkflowEngine(sleep_fn=sleeps.append).run(spec, {})

        self.assertEqual(len(attempts), 3)
        self.assertTrue(result.state["ok"])
        self.assertEqual(len(sleeps), 2)  # slept between attempts 1->2 and 2->3

    def test_step_exhausts_retries_and_raises(self):
        def always_fails(state):
            raise RuntimeError("boom")

        spec = WorkflowSpec(
            "wf",
            [Step("bad", always_fails, retry_policy=RetryPolicy(max_attempts=2))],
            start="bad",
        )

        with self.assertRaises(StepExecutionError) as ctx:
            WorkflowEngine(sleep_fn=lambda s: None).run(spec, {})

        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)


class TestWorkflowEngineCycleGuard(unittest.TestCase):
    def test_infinite_branch_cycle_raises_max_steps_exceeded(self):
        steps = [Step("loop", lambda s: {}, branch=lambda s: "loop")]
        spec = WorkflowSpec("wf", steps, start="loop")

        with self.assertRaises(MaxStepsExceededError):
            WorkflowEngine().run(spec, {}, max_steps=10)


if __name__ == "__main__":
    unittest.main()
