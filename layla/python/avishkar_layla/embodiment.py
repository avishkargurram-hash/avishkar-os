"""EmbodimentController -- Mission Layla Parts 8/15/17/21 (Browser/
Computer Control, Application Control, Android/ADB, IoT, Sensors,
Robotics, Home Assistant, MQTT). See CONTRACT.md SS29.

STATUS: CONTRACT / INTEGRATION BOUNDARY ONLY. No browser automation,
OS-level input control, ADB, MQTT, or Home Assistant backend is wired
here. This mission's own forensic audit found real, working code for
every one of these capabilities in GENESIS -- and found its safety
gates comprehensively non-functional: a tool-naming mismatch that made
its "existential sovereignty lock" never actually fire for real
shell-exec/filesystem-delete/browser-automation/ADB calls,
`permissions.json` explicitly *allowing* those same actions by their
real tool IDs, and an identity-verification check that fails open due
to a type-mismatch bug. Building an equally-capable but *actually
safe* equivalent is real, dedicated security-engineering work, not
compressible into this pass -- see docs/mission-layla-1-plan.md SS17.

Per the directive's own fallback: this module is the "correct
production-grade contract and integration boundary." Unlike GENESIS's
gates, the risk/approval check here is **structural, not name-matched**
-- `request()` itself computes risk via Layla's own real
`risk.classify_risk()` and enforces `ApprovalManager` for any non-LOW
risk *before* an executor is ever looked up or called, so there is no
tool-naming table to fall out of sync with the real capability set (the
exact bug class that silently disabled GENESIS's own governor). Zero
executors are registered by default -- calling `request()` for an
unconfigured capability raises `EmbodimentCapabilityNotConfiguredError`
after the risk/approval check has already run, so even discovering
"is this capability configured" requires clearing the same gate a real
call would.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .approval import ApprovalManager
from .errors import LaylaError
from .risk import classify_risk
from .types import RISK_HIGH, RISK_LOW

EMBODIMENT_BROWSER = "browser"
EMBODIMENT_COMPUTER_CONTROL = "computer_control"
EMBODIMENT_APPLICATION_CONTROL = "application_control"
EMBODIMENT_ADB = "adb"
EMBODIMENT_IOT = "iot"
EMBODIMENT_SENSORS = "sensors"
EMBODIMENT_ROBOTICS = "robotics"
EMBODIMENT_HOME_ASSISTANT = "home_assistant"
EMBODIMENT_MQTT = "mqtt"

EMBODIMENT_CAPABILITIES = (
    EMBODIMENT_BROWSER, EMBODIMENT_COMPUTER_CONTROL, EMBODIMENT_APPLICATION_CONTROL, EMBODIMENT_ADB,
    EMBODIMENT_IOT, EMBODIMENT_SENSORS, EMBODIMENT_ROBOTICS, EMBODIMENT_HOME_ASSISTANT, EMBODIMENT_MQTT,
)

# Fail-closed default (matching execution.py's classify_operation()):
# every embodiment capability defaults to physical/host-affecting until
# proven otherwise -- Mission Layla Part 15's own "physical-world
# operations must default to fail-closed."
#
# EMBODIMENT_MQTT added here in Directive D Part VIII (ADR-0035): a
# real `mqtt.MQTTBridge` (see mqtt/client.py) is what actually
# publishes to a real broker, and an MQTT `publish` is routinely how
# real physical devices (smart plugs, locks, actuators -- often the
# same devices Home Assistant itself controls under the hood) are
# commanded. Text-classifying "mqtt publish {topic: ..., payload: ...}"
# alone cannot reliably tell "publish a benign sensor-poll request"
# apart from "publish a command that unlocks a door," so -- exactly
# like EMBODIMENT_HOME_ASSISTANT/EMBODIMENT_ADB/EMBODIMENT_COMPUTER_CONTROL
# -- it is escalated by construction rather than trusted to the
# general-purpose text classifier. Adding a capability here is a
# strictly MORE conservative change (a LOW-risk classification simply
# becomes gated, never the reverse), so no existing caller that relied
# on EMBODIMENT_MQTT being ungated could have existed to break --
# confirmed by grepping the whole tree before this change.
_DEFAULT_HIGH_RISK_CAPABILITIES = frozenset({
    EMBODIMENT_COMPUTER_CONTROL, EMBODIMENT_ADB, EMBODIMENT_ROBOTICS, EMBODIMENT_HOME_ASSISTANT,
    EMBODIMENT_MQTT,
})


class UnknownEmbodimentCapabilityError(LaylaError):
    """request()/register_executor() referenced a capability outside
    EMBODIMENT_CAPABILITIES.
    """


class EmbodimentCapabilityNotConfiguredError(LaylaError):
    """request() cleared risk/approval but found no real executor
    registered for this capability -- the documented ADAPTER READY
    boundary. Deliberately raised *after* the gate, not before, so
    "is this configured" is never itself a way to probe capabilities
    without authorization.
    """


class EmbodimentNotApprovedError(LaylaError):
    """A non-LOW-risk embodiment request was not granted approval --
    request() refuses to call any executor in this case, regardless of
    whether one is configured.
    """


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class EmbodimentResult:
    capability: str
    action: str
    status: str  # "completed" | "denied"
    output: Optional[Any] = None
    risk_level: str = RISK_LOW
    completed_at: str = ""


EmbodimentExecutor = Callable[[str, Mapping[str, Any]], Any]  # (action, parameters) -> output


class EmbodimentController:
    def __init__(
        self, *, approval_manager: Optional[ApprovalManager] = None, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._approval = approval_manager
        self._executors: Dict[str, EmbodimentExecutor] = {}
        self._clock = clock

    def register_executor(self, capability: str, executor: EmbodimentExecutor) -> None:
        if capability not in EMBODIMENT_CAPABILITIES:
            raise UnknownEmbodimentCapabilityError(
                f"unknown embodiment capability {capability!r} -- expected one of {EMBODIMENT_CAPABILITIES}"
            )
        self._executors[capability] = executor

    def configured_capabilities(self) -> Tuple[str, ...]:
        return tuple(self._executors.keys())

    def request(
        self, capability: str, action: str, parameters: Mapping[str, Any], *, task_id: str,
        principal_id: Optional[str] = None,
    ) -> EmbodimentResult:
        """Capability Resolver -> Risk Classifier -> Authorization ->
        Approval Policy -> Sandboxed Tool -> Execution -> Verification
        -- Mission Layla Part 8's exact required chain. Risk is always
        computed here, from the real action/parameters text, never
        accepted as a caller-asserted value (that would let a caller
        simply claim LOW risk for a dangerous action -- exactly the
        kind of trust-the-caller gap this mission's audit found
        exploitable in GENESIS).
        """
        if capability not in EMBODIMENT_CAPABILITIES:
            raise UnknownEmbodimentCapabilityError(
                f"unknown embodiment capability {capability!r} -- expected one of {EMBODIMENT_CAPABILITIES}"
            )

        description = f"{capability} {action} {dict(parameters)}"
        risk_level = classify_risk(description)
        if risk_level == RISK_LOW and capability in _DEFAULT_HIGH_RISK_CAPABILITIES:
            # classify_risk() is a general-purpose text classifier; it
            # doesn't know these capabilities are physical/host-
            # affecting by construction. Escalate explicitly rather
            # than trust a pattern-matcher that was never told about
            # embodiment capabilities specifically.
            risk_level = RISK_HIGH

        if risk_level != RISK_LOW:
            if self._approval is None:
                raise EmbodimentNotApprovedError(
                    f"{capability}.{action} classified {risk_level} risk, but no ApprovalManager is "
                    f"wired -- fail closed, never silently allowed"
                )
            approval = self._approval.request(task_id, description, risk_level, requested_by=principal_id)
            if approval.status != "granted":
                return EmbodimentResult(
                    capability=capability, action=action, status="denied", risk_level=risk_level,
                    completed_at=_now(),
                )

        executor = self._executors.get(capability)
        if executor is None:
            raise EmbodimentCapabilityNotConfiguredError(
                f"embodiment capability {capability!r} has no real executor configured -- this is the "
                f"documented ADAPTER READY boundary (CONTRACT.md SS29): wire a real, sandboxed executor "
                f"via register_executor() before using this capability in production. Cleared risk/"
                f"approval first ({risk_level}) -- this error is about missing implementation, not "
                f"missing authorization."
            )

        output = executor(action, parameters)
        return EmbodimentResult(
            capability=capability, action=action, status="completed", output=output,
            risk_level=risk_level, completed_at=_now(),
        )
