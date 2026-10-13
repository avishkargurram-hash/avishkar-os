import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy, PersonalModel, SensitiveCategoryNotConfirmedError
from avishkar_layla.life_os import LifeOS


def _life_os():
    return LifeOS(PersonalModel(LaylaMemoryPolicy(InMemoryMemoryPolicy())))


class TestLifeOSWork(unittest.TestCase):
    def test_add_goal_and_task(self):
        life_os = _life_os()
        life_os.add_goal("g1", "ship Mission Layla foundation")
        life_os.add_task("t1", "write tests", due="2026-08-20")

        self.assertEqual(len(life_os.list_tasks()), 1)
        self.assertEqual(life_os.list_tasks()["t1"].value["description"], "write tests")


class TestLifeOSSensitiveCategories(unittest.TestCase):
    def test_health_requires_confirmation(self):
        life_os = _life_os()
        with self.assertRaises(SensitiveCategoryNotConfirmedError):
            life_os.log_health("h1", "annual checkup completed", confirmed=False)

    def test_health_with_confirmation_succeeds(self):
        life_os = _life_os()
        fact = life_os.log_health("h1", "annual checkup completed", confirmed=True)
        self.assertEqual(fact.value, "annual checkup completed")

    def test_finance_requires_confirmation(self):
        life_os = _life_os()
        with self.assertRaises(SensitiveCategoryNotConfirmedError):
            life_os.log_finance("f1", "quarterly review", 1000.0, confirmed=False)

    def test_finance_with_confirmation_succeeds(self):
        life_os = _life_os()
        fact = life_os.log_finance("f1", "quarterly review", 1000.0, confirmed=True)
        self.assertEqual(fact.value["amount"], 1000.0)


class TestLifeOSScheduling(unittest.TestCase):
    def test_upcoming_appointments_are_filtered_and_sorted(self):
        life_os = _life_os()
        life_os.add_appointment("a1", "board meeting", when="2026-09-01T10:00:00+00:00")
        life_os.add_appointment("a2", "1:1", when="2026-08-25T10:00:00+00:00")
        life_os.add_appointment("a3", "past event", when="2026-01-01T10:00:00+00:00")

        upcoming = life_os.list_upcoming_appointments(now="2026-08-16T00:00:00+00:00")

        self.assertEqual([f.value["description"] for f in upcoming], ["1:1", "board meeting"])

    def test_due_reminders_are_filtered_and_sorted(self):
        life_os = _life_os()
        life_os.add_reminder("r1", "renew passport", when="2026-08-10T00:00:00+00:00")
        life_os.add_reminder("r2", "future reminder", when="2026-12-01T00:00:00+00:00")

        due = life_os.list_due_reminders(now="2026-08-16T00:00:00+00:00")

        self.assertEqual([f.value["message"] for f in due], ["renew passport"])

    def test_no_appointments_returns_empty(self):
        life_os = _life_os()
        self.assertEqual(life_os.list_upcoming_appointments(), ())


class TestLifeOSLifeAndTravel(unittest.TestCase):
    def test_add_habit_life_event_travel_plan(self):
        life_os = _life_os()
        life_os.add_habit("morning-review", "review daily brief each morning")
        life_os.add_life_event("e1", "moved to new office", when="2026-07-01")
        life_os.add_travel_plan("trip-1", "SF", when="2026-09-10")

        # Real round-trip through the underlying PersonalModel, not fabricated.
        self.assertEqual(life_os._model.get("habits", "morning-review").value, "review daily brief each morning")
        self.assertEqual(life_os._model.get("life_events", "e1").value["description"], "moved to new office")
        self.assertEqual(life_os._model.get("travel", "trip-1").value["destination"], "SF")


if __name__ == "__main__":
    unittest.main()
