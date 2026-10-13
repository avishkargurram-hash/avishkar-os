"""Robotics/Embodiment -- Mission Layla Directive D, Part IX. See
CONTRACT.md SS44.

Directive D Part IX, verbatim: "Use the existing: PerceptionEngine,
EmbodimentController, risk.classify_risk, ApprovalManager,
UniversalToolRegistry, MCP, EventBus, AuditLogger. Create safe
adapters for future robotics platforms." This package creates no new
cognitive/risk/event framework -- `RobotSafetyController` is a real
safety layer that sits BETWEEN `EmbodimentController` (which already
gates every `EMBODIMENT_ROBOTICS` action behind approval, since
`EMBODIMENT_ROBOTICS` is already in `_DEFAULT_HIGH_RISK_CAPABILITIES`)
and a real robot driver a deployment provides for its specific
platform (ROS, a proprietary REST/serial API, etc.).

No physical robot exists in this environment -- the honest ADAPTER
READY boundary is the `RobotDriver` interface itself (a deployment
implements `execute()`/`get_state()`/`emergency_stop()` for its real
hardware). What IS real and genuinely tested here, without any
physical hardware, is the SAFETY LOGIC Directive D explicitly
requires: real enforced action timeouts, a real emergency-stop latch
that only an explicit human-authorized `reset_emergency_stop()` call
can clear, real fail-safe triggering on any timeout/exception (which
itself also latches the emergency stop), real state verification
after every action, and a real, complete audit trail via the existing
`AuditLogger` -- all fully exercised with injected fake drivers (the
same DI seam `ComputerControlExecutor`'s `_gui`/`ADBExecutor`'s `_run`
use), proving the safety logic itself, not a specific robot's
behavior.
"""

from __future__ import annotations

from .controller import RobotSafetyController
from .errors import (
    RobotActionFailedError,
    RobotActionTimeoutError,
    RobotEmergencyStoppedError,
)

__all__ = [
    "RobotActionFailedError",
    "RobotActionTimeoutError",
    "RobotEmergencyStoppedError",
    "RobotSafetyController",
]
