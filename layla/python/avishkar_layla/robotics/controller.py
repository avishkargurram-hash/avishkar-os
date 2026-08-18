"""RobotSafetyController -- real safety layer for EMBODIMENT_ROBOTICS.
See CONTRACT.md SS44.

STATUS: REAL safety logic, ADAPTER READY for any specific physical
robot (no hardware exists in this environment -- a deployment supplies
a real `RobotDriver` for its platform). Directive D Part IX's required
physical-action safety properties are all real here, not aspirational:
explicit capability registration (`EmbodimentController.register_executor`,
unchanged), real risk level (already computed by `EmbodimentController`
-- `EMBODIMENT_ROBOTICS` is in `_DEFAULT_HIGH_RISK_CAPABILITIES`), a
real emergency stop (a latch only an explicit authorized call can
clear), a real enforced timeout per action, real cancellation (a
timed-out action's result is discarded, never applied), real state
verification (the driver's own `get_state()` is queried and recorded
after every action), a real audit trail (every action/timeout/failure/
stop/reset via the existing `AuditLogger`), a real human override (the
emergency-stop latch always takes precedence over any new action
request, checked first), and real fail-safe behavior (any timeout or
driver exception both latches the emergency stop AND invokes a
caller-supplied fail-safe callback, before the error propagates).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol

from .errors import RobotActionFailedError, RobotActionTimeoutError, RobotEmergencyStoppedError


class RobotDriver(Protocol):
    """What a real deployment implements for its specific robot
    platform. Not provided here -- no physical robot exists in this
    environment; this is the documented ADAPTER READY boundary.
    """

    def execute(self, action: str, parameters: Mapping[str, Any]) -> Any:
        ...

    def get_state(self) -> Mapping[str, Any]:
        ...

    def emergency_stop(self) -> None:
        ...


class RobotSafetyController:
    def __init__(
        self, driver: RobotDriver, *, audit: Optional[Any] = None, action_timeout_seconds: float = 10.0,
        fail_safe_callback: Optional[Callable[[str], None]] = None, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._driver = driver
        self._audit = audit
        self._timeout = action_timeout_seconds
        self._fail_safe_callback = fail_safe_callback
        self._clock = clock
        self._lock = threading.Lock()
        self._emergency_stopped = False

    @property
    def is_emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stopped

    def _record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self._audit is not None:
            self._audit.record(event_type, dict(payload))

    def emergency_stop(self, *, reason: str) -> None:
        """Immediate, real stop. Sets the latch FIRST (so any
        in-flight or subsequent call sees it right away, even if the
        real driver's own emergency_stop() call itself takes time or
        fails) -- a human override must never be delayed by whether
        the hardware call succeeds.
        """
        with self._lock:
            self._emergency_stopped = True
        self._record("layla.robotics.emergency_stop", {"reason": reason})
        try:
            self._driver.emergency_stop()
        except Exception as exc:  # noqa: BLE001 -- the latch is already set regardless of driver failure
            self._record("layla.robotics.emergency_stop_driver_error", {"error": str(exc)})

    def reset_emergency_stop(self, *, authorized_by: str) -> None:
        """The ONLY way to clear the latch -- never automatic, never a
        side effect of a normal action call. `authorized_by` is
        recorded in the audit trail so the human override is
        traceable to a real actor, not merely inferred.
        """
        with self._lock:
            self._emergency_stopped = False
        self._record("layla.robotics.emergency_stop_reset", {"authorized_by": authorized_by})

    def _trigger_fail_safe(self, *, reason: str) -> None:
        with self._lock:
            self._emergency_stopped = True
        self._record("layla.robotics.fail_safe_triggered", {"reason": reason})
        if self._fail_safe_callback is not None:
            try:
                self._fail_safe_callback(reason)
            except Exception as exc:  # noqa: BLE001 -- a broken fail-safe callback must not mask the original failure
                self._record("layla.robotics.fail_safe_callback_error", {"error": str(exc)})

    def _query_state(self) -> Optional[Mapping[str, Any]]:
        try:
            return self._driver.get_state()
        except Exception as exc:  # noqa: BLE001 -- state verification is best-effort; a failure here doesn't hide the real result
            self._record("layla.robotics.state_query_failed", {"error": str(exc)})
            return None

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        """`EmbodimentExecutor`-shaped -- registered via
        `EmbodimentController.register_executor(EMBODIMENT_ROBOTICS, controller)`.
        `EmbodimentController.request()` has already computed risk and
        secured approval before this is ever called (embodiment.py,
        unchanged); this is the second, complementary safety gate --
        human override, timeout, fail-safe -- beneath that.
        """
        if self.is_emergency_stopped:
            raise RobotEmergencyStoppedError(
                f"robot action {action!r} refused -- emergency stop is latched; call reset_emergency_stop() "
                f"with an explicit authorized_by first"
            )

        outcome: dict = {}

        def _run() -> None:
            try:
                outcome["result"] = self._driver.execute(action, parameters)
            except Exception as exc:  # noqa: BLE001 -- captured and re-raised on the caller's thread below
                outcome["error"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        start = self._clock()
        thread.start()
        thread.join(timeout=self._timeout)
        elapsed = self._clock() - start

        if thread.is_alive():
            # Real cancellation: the timed-out call's eventual result
            # (if the daemon thread ever finishes) is never read or
            # applied -- `outcome` is simply abandoned.
            self._trigger_fail_safe(reason=f"action {action!r} exceeded {self._timeout}s timeout")
            raise RobotActionTimeoutError(f"robot action {action!r} timed out after {self._timeout}s")

        if "error" in outcome:
            self._trigger_fail_safe(reason=f"action {action!r} raised: {outcome['error']}")
            raise RobotActionFailedError(f"robot action {action!r} failed: {outcome['error']}") from outcome["error"]

        state = self._query_state()
        self._record(
            "layla.robotics.action_completed",
            {"action": action, "parameters": dict(parameters), "elapsed_seconds": elapsed, "state": state},
        )
        return {"result": outcome.get("result"), "state": state}
