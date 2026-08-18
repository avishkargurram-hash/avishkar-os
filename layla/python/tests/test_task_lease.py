import threading
import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.task_lease import TaskLeaseManager


def _manager(clock=lambda: 1000.0):
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return TaskLeaseManager(memory, clock=clock)


class TestTaskLeaseAcquire(unittest.TestCase):
    def test_first_acquire_succeeds(self):
        manager = _manager()
        self.assertTrue(manager.acquire("task-1", "worker-a"))

    def test_second_worker_cannot_acquire_an_unexpired_lease(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a", lease_seconds=300.0)
        self.assertFalse(manager.acquire("task-1", "worker-b"))

    def test_same_worker_can_reacquire_idempotently(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a")
        self.assertTrue(manager.acquire("task-1", "worker-a"))

    def test_a_different_worker_can_acquire_after_real_expiry(self):
        clock = [1000.0]
        manager = _manager(clock=lambda: clock[0])
        manager.acquire("task-1", "worker-a", lease_seconds=10.0)

        clock[0] = 1011.0  # 11 real seconds later -- past the 10s lease

        self.assertTrue(manager.acquire("task-1", "worker-b"))
        lease = manager.get_lease("task-1")
        self.assertEqual(lease.worker_id, "worker-b")


class TestTaskLeaseRenew(unittest.TestCase):
    def test_owner_can_renew(self):
        clock = [1000.0]
        manager = _manager(clock=lambda: clock[0])
        manager.acquire("task-1", "worker-a", lease_seconds=10.0)

        clock[0] = 1005.0
        self.assertTrue(manager.renew("task-1", "worker-a", lease_seconds=10.0))

        lease = manager.get_lease("task-1")
        self.assertEqual(lease.expires_at, 1015.0)

    def test_non_owner_cannot_renew(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a")
        self.assertFalse(manager.renew("task-1", "worker-b"))

    def test_renewing_a_never_acquired_task_fails(self):
        manager = _manager()
        self.assertFalse(manager.renew("task-1", "worker-a"))


class TestTaskLeaseRelease(unittest.TestCase):
    def test_owner_can_release_and_another_worker_can_then_acquire(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a", lease_seconds=300.0)
        self.assertTrue(manager.release("task-1", "worker-a"))

        self.assertTrue(manager.acquire("task-1", "worker-b"))  # no need to wait out the lease

    def test_non_owner_cannot_release(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a")
        self.assertFalse(manager.release("task-1", "worker-b"))
        self.assertIsNotNone(manager.get_lease("task-1"))  # still held by worker-a


class TestTaskLeaseStaleness(unittest.TestCase):
    def test_never_leased_task_is_not_stale(self):
        manager = _manager()
        self.assertFalse(manager.is_stale("never-leased"))

    def test_unexpired_lease_is_not_stale(self):
        manager = _manager()
        manager.acquire("task-1", "worker-a", lease_seconds=300.0)
        self.assertFalse(manager.is_stale("task-1"))

    def test_expired_lease_is_stale(self):
        clock = [1000.0]
        manager = _manager(clock=lambda: clock[0])
        manager.acquire("task-1", "worker-a", lease_seconds=10.0)
        clock[0] = 1020.0
        self.assertTrue(manager.is_stale("task-1"))

    def test_find_stale_leases_filters_a_real_batch(self):
        clock = [1000.0]
        manager = _manager(clock=lambda: clock[0])
        manager.acquire("stuck-task", "worker-a", lease_seconds=10.0)
        manager.acquire("active-task", "worker-b", lease_seconds=300.0)

        clock[0] = 1020.0
        stale = manager.find_stale_leases(["stuck-task", "active-task", "never-leased"])

        self.assertEqual(stale, ("stuck-task",))


class TestTaskLeaseRealConcurrency(unittest.TestCase):
    def test_only_one_of_many_concurrent_acquirers_wins(self):
        """A real threading test -- genuine concurrent acquire() calls
        from multiple real threads racing for the same task, proving
        the internal lock actually serializes them (within this one
        process -- see module docstring for the documented
        multi-process scope limit).
        """
        manager = _manager()
        results = []
        results_lock = threading.Lock()

        def _try_acquire(worker_id):
            won = manager.acquire("contested-task", worker_id, lease_seconds=300.0)
            with results_lock:
                results.append((worker_id, won))

        threads = [threading.Thread(target=_try_acquire, args=(f"worker-{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [worker_id for worker_id, won in results if won]
        self.assertEqual(len(winners), 1)  # exactly one real winner, no double-acquire


if __name__ == "__main__":
    unittest.main()
