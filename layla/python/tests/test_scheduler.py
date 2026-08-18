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


class TestSchedulerFailureIsolation(unittest.TestCase):
    """Directive D Part XI (ADR-0038): one job's real exception must
    never crash tick() or prevent other due jobs from running.
    """

    def test_a_raising_job_does_not_crash_tick(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])

        def _boom():
            raise RuntimeError("sensor read failed")

        job_id = scheduler.schedule_once(1.0, _boom)

        fired = scheduler.tick(now=1.0)  # must not raise
        self.assertEqual(fired, (job_id,))  # attempted (and failed) -- still reported as fired

    def test_a_raising_job_does_not_prevent_other_due_jobs_from_running(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []

        def _boom():
            raise RuntimeError("boom")

        scheduler.schedule_once(1.0, _boom)
        scheduler.schedule_once(1.0, lambda: calls.append("ok"))

        fired = scheduler.tick(now=1.0)

        self.assertEqual(len(fired), 2)
        self.assertEqual(calls, ["ok"])

    def test_failure_count_increments_on_a_real_exception(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])

        def _boom():
            raise RuntimeError("boom")

        job_id = scheduler.schedule_recurring(10.0, _boom, start_at=1.0)
        scheduler.tick(now=1.0)
        self.assertEqual(scheduler.failure_count(job_id), 1)
        scheduler.tick(now=11.0)
        self.assertEqual(scheduler.failure_count(job_id), 2)

    def test_a_real_success_resets_the_failure_streak(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        state = {"fail": True}

        def _sometimes_fails():
            if state["fail"]:
                raise RuntimeError("boom")

        job_id = scheduler.schedule_recurring(10.0, _sometimes_fails, start_at=1.0)
        scheduler.tick(now=1.0)
        self.assertEqual(scheduler.failure_count(job_id), 1)

        state["fail"] = False
        scheduler.tick(now=11.0)
        self.assertEqual(scheduler.failure_count(job_id), 0)

    def test_on_job_error_callback_receives_the_real_job_id_and_exception(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0], on_job_error=lambda job_id, exc: seen.append((job_id, exc)))
        seen = []

        def _boom():
            raise ValueError("bad input")

        job_id = scheduler.schedule_once(1.0, _boom)
        scheduler.tick(now=1.0)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], job_id)
        self.assertIsInstance(seen[0][1], ValueError)

    def test_a_broken_on_job_error_callback_does_not_crash_tick(self):
        clock = [0.0]

        def _broken_handler(job_id, exc):
            raise RuntimeError("the error handler itself is broken")

        scheduler = Scheduler(clock=lambda: clock[0], on_job_error=_broken_handler)

        def _boom():
            raise RuntimeError("original failure")

        scheduler.schedule_once(1.0, _boom)
        fired = scheduler.tick(now=1.0)  # must not raise despite the broken handler
        self.assertEqual(len(fired), 1)


class TestSchedulerDeadLetter(unittest.TestCase):
    def test_job_is_dead_lettered_after_max_consecutive_failures(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0], max_consecutive_failures=3)

        def _boom():
            raise RuntimeError("persistent failure")

        job_id = scheduler.schedule_recurring(1.0, _boom, start_at=1.0)
        scheduler.tick(now=1.0)
        scheduler.tick(now=2.0)
        self.assertIn(job_id, scheduler.pending_job_ids())  # not dead-lettered yet

        scheduler.tick(now=3.0)  # third consecutive failure crosses the threshold

        self.assertNotIn(job_id, scheduler.pending_job_ids())
        dead_letter = scheduler.dead_lettered_jobs()
        self.assertIn(job_id, dead_letter)
        self.assertIn("persistent failure", dead_letter[job_id])

    def test_a_dead_lettered_job_never_fires_again(self):
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0], max_consecutive_failures=1)
        calls = []

        def _boom():
            calls.append(1)
            raise RuntimeError("boom")

        scheduler.schedule_recurring(1.0, _boom, start_at=1.0)
        scheduler.tick(now=1.0)  # fails once -- immediately dead-lettered
        scheduler.tick(now=2.0)
        scheduler.tick(now=3.0)

        self.assertEqual(len(calls), 1)  # never called again after dead-lettering

    def test_without_max_consecutive_failures_a_job_is_retried_forever(self):
        """The default (max_consecutive_failures=None) preserves the
        exact pre-existing behavior -- a recurring job keeps being
        rescheduled no matter how many times it fails.
        """
        clock = [0.0]
        scheduler = Scheduler(clock=lambda: clock[0])
        calls = []

        def _boom():
            calls.append(1)
            raise RuntimeError("boom")

        job_id = scheduler.schedule_recurring(1.0, _boom, start_at=1.0)
        scheduler.tick(now=1.0)
        scheduler.tick(now=2.0)
        scheduler.tick(now=3.0)

        self.assertEqual(len(calls), 3)
        self.assertIn(job_id, scheduler.pending_job_ids())
        self.assertEqual(scheduler.dead_lettered_jobs(), {})


if __name__ == "__main__":
    unittest.main()
