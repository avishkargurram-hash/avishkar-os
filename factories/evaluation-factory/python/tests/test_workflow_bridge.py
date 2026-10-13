import unittest

from avishkar_workflow import WorkflowResult

from avishkar_evaluation import EvalCase, EvalSuite, evaluate_workflow_result, exact_match_scorer


class TestEvaluateWorkflowResult(unittest.TestCase):
    def test_scores_the_named_output_key(self):
        result = WorkflowResult(state={"output": "the answer"}, history=("step1",), status="completed")
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="the answer"),))

        report = evaluate_workflow_result(result, suite, exact_match_scorer)

        self.assertEqual(report.average, 1.0)

    def test_custom_output_key(self):
        result = WorkflowResult(state={"answer_text": "hi"}, history=(), status="completed")
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="hi"),))

        report = evaluate_workflow_result(result, suite, exact_match_scorer, output_key="answer_text")

        self.assertEqual(report.average, 1.0)


if __name__ == "__main__":
    unittest.main()
