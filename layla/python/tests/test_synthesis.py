import unittest

from avishkar_layla.errors import UnresolvedConflictError
from avishkar_layla.synthesis import ConflictResolver, ExecutiveSynthesizer, ResultValidator
from avishkar_layla.types import DelegationRecord


def _record(step_id, agent_name, status="completed", output=None):
    return DelegationRecord(step_id=step_id, agent_name=agent_name, status=status, output=output)


class TestResultValidator(unittest.TestCase):
    def test_all_completed(self):
        records = [_record("s1", "a", output="x"), _record("s2", "b", output="y")]
        report = ResultValidator().validate(records)
        self.assertTrue(report.all_completed)
        self.assertEqual(report.failing, ())

    def test_some_failing(self):
        records = [_record("s1", "a", output="x"), _record("s2", "b", status="failed")]
        report = ResultValidator().validate(records)
        self.assertFalse(report.all_completed)
        self.assertEqual(report.failing, ("s2",))


class TestConflictResolver(unittest.TestCase):
    def test_similar_outputs_are_not_a_conflict(self):
        records = [
            _record("s1", "a", output="The vendor contract requires a passing test suite and a code review."),
            _record("s2", "b", output="This contract requires a passing test suite and code review before merge."),
        ]
        conflicts = ConflictResolver().detect(records)
        self.assertEqual(conflicts, ())

    def test_dissimilar_outputs_are_flagged_as_conflict(self):
        records = [
            _record("s1", "legal-agent", output="This contract is high risk due to unlimited liability."),
            _record("s2", "finance-agent", output="Preheat the oven to 350 degrees before baking."),
        ]
        conflicts = ConflictResolver().detect(records)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].step_ids, ("s1", "s2"))

    def test_non_completed_records_are_ignored(self):
        records = [
            _record("s1", "a", output="x"),
            _record("s2", "b", status="failed"),
        ]
        conflicts = ConflictResolver().detect(records)
        self.assertEqual(conflicts, ())


class TestExecutiveSynthesizer(unittest.TestCase):
    def test_synthesizes_completed_results(self):
        records = [_record("s1", "legal-agent", output="looks fine"), _record("s2", "finance-agent", output="ROI positive")]
        summary = ExecutiveSynthesizer().synthesize(records, conflicts=())
        self.assertIn("legal-agent", summary)
        self.assertIn("finance-agent", summary)

    def test_refuses_to_synthesize_silently_with_unresolved_conflicts(self):
        records = [_record("s1", "a", output="x"), _record("s2", "b", output="y")]
        conflicts = ConflictResolver().detect([
            _record("s1", "a", output="This contract is high risk."),
            _record("s2", "b", output="Preheat the oven to 350 degrees."),
        ])
        with self.assertRaises(UnresolvedConflictError):
            ExecutiveSynthesizer().synthesize(records, conflicts)

    def test_allow_unresolved_bypasses_the_refusal(self):
        records = [_record("s1", "a", output="x"), _record("s2", "b", output="y")]
        conflicts = (object(),)  # any non-empty conflicts collection
        summary = ExecutiveSynthesizer().synthesize(records, conflicts, allow_unresolved=True)
        self.assertIn("x", summary)

    def test_no_completed_results_returns_honest_message(self):
        records = [_record("s1", "a", status="failed")]
        summary = ExecutiveSynthesizer().synthesize(records, conflicts=())
        self.assertEqual(summary, "No delegated work completed successfully.")


if __name__ == "__main__":
    unittest.main()
