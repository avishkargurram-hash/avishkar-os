import unittest

from avishkar_layla.scheduler import Scheduler


class TestScheduler(unittest.TestCase):
    def test_one_shot_job_fires_once_at_or_after_its_time(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        job_id = scheduler.schedule_once(10.0, lambda: calls.append("fired"))

        self.assertEqual(scheduler.tick(now=5.0), ())  # too early -- not fired yet
        self.assertEqual(calls, [])

        fired = scheduler.tick(now=10.0)

        self.assertEqual(fired, (job_id,))
        self.assertEqual(calls, ["fired"])

    def test_one_shot_job_does_not_fire_twice(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        scheduler.schedule_once(10.0, lambda: calls.append(1))

        scheduler.tick(now=10.0)
        scheduler.tick(now=20.0)

        self.assertEqual(len(calls), 1)

    def test_recurring_job_fires_repeatedly(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        scheduler.schedule_recurring(10.0, lambda: calls.append(1), start_at=10.0)

        scheduler.tick(now=10.0)
        scheduler.tick(now=20.0)
        scheduler.tick(now=30.0)

        self.assertEqual(len(calls), 3)

    def test_cancel_prevents_future_firing(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        job_id = scheduler.schedule_once(10.0, lambda: calls.append(1))

        cancelled = scheduler.cancel(job_id)
        scheduler.tick(now=10.0)

        self.assertTrue(cancelled)
        self.assertEqual(calls, [])

    def test_cancel_unknown_job_returns_false(self):
        scheduler = Scheduler(clock=lambda: 0.0)
        self.assertFalse(scheduler.cancel("job-does-not-exist"))

    def test_tick_returns_fired_job_ids(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        job_id = scheduler.schedule_once(5.0, lambda: None)

        fired = scheduler.tick(now=5.0)

        self.assertEqual(fired, (job_id,))

    def test_multiple_due_jobs_all_fire_in_one_tick(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        scheduler.schedule_once(1.0, lambda: calls.append("a"))
        scheduler.schedule_once(2.0, lambda: calls.append("b"))

        fired = scheduler.tick(now=5.0)

        self.assertEqual(len(fired), 2)
        self.assertEqual(set(calls), {"a", "b"})

    def test_uses_injected_clock_when_now_not_given(self):
        clock = [100.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []
        scheduler.schedule_once(100.0, lambda: calls.append(1))

        scheduler.tick()  # no explicit now -- uses clock()

        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
