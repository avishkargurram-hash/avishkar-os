import unittest

from avishkar_security import SECURITY_CHECKLIST, MissingAnswerError, UnknownChecklistItemError, run_checklist


def _all_pass_answers():
    return {item.id: True for item in SECURITY_CHECKLIST}


class TestRunChecklist(unittest.TestCase):
    def test_all_pass_gives_passed_report(self):
        report = run_checklist("demo-module", _all_pass_answers())
        self.assertTrue(report.passed)
        self.assertEqual(report.failing, ())

    def test_one_failure_marks_report_not_passed(self):
        answers = _all_pass_answers()
        answers["no-committed-secrets"] = False
        report = run_checklist("demo-module", answers, notes={"no-committed-secrets": "found one, fixing"})

        self.assertFalse(report.passed)
        self.assertEqual(len(report.failing), 1)
        self.assertEqual(report.failing[0].note, "found one, fixing")

    def test_missing_answer_raises(self):
        answers = _all_pass_answers()
        del answers["audit-logging"]
        with self.assertRaises(MissingAnswerError):
            run_checklist("demo-module", answers)

    def test_unknown_answer_id_raises(self):
        answers = _all_pass_answers()
        answers["not-a-real-item"] = True
        with self.assertRaises(UnknownChecklistItemError):
            run_checklist("demo-module", answers)

    def test_report_covers_every_checklist_item(self):
        report = run_checklist("demo-module", _all_pass_answers())
        self.assertEqual({r.item_id for r in report.results}, {item.id for item in SECURITY_CHECKLIST})


if __name__ == "__main__":
    unittest.main()
