"""Environmental Awareness -- Mission Layla Directive D, Part VI. See
CONTRACT.md SS38.

Sensor -> Event -> EventBus -> Perception/Context -> Layla -> Decision
-> Action (Directive D's exact required chain). "Do NOT poll an LLM
continuously. Use events, schedules, thresholds and state changes to
wake Layla intelligence only when required" -- every piece here is
built around that rule: `SensorMonitor.check()` is cheap, real,
non-LLM Python (a sensor read + a threshold/change comparison),
invoked on a `Scheduler` tick (already real, already exists -- not a
new polling loop), and only publishes a real `avishkar_core.EventBus`
event when something genuinely changed. Nothing here calls
`ExecutiveRuntime.handle_event()` directly; `EnvironmentalChangeEvaluator`
is a real `TriggerEvaluator` (`proactive.py`, ADR-0026) a deployment can
wire into `ProactiveEngine`'s existing `extra_evaluators` -- the same
evidence-only, capped-at-OBSERVE pattern every other built-in evaluator
uses, never a bypass of `handle_event()`'s risk/approval pipeline.

Sensors are real and locally-backed (no camera/microphone -- those are
already covered by `voice`/`vision`, Directive D Parts I/II): idle
time, battery/power state, system load, and real network-reachability
(a genuine socket connection attempt, not just an interface-up flag).
"""

from __future__ import annotations

from .context import EnvironmentalChangeEvaluator, EnvironmentalEventBuffer
from .errors import SensorUnavailableError
from .event_translation import ENVIRONMENT_EVENT_PREFIX, SensorMonitor
from .sensors import BatterySensor, IdleTimeSensor, NetworkConnectivitySensor, Sensor, SensorReading, SystemLoadSensor

__all__ = [
    "ENVIRONMENT_EVENT_PREFIX",
    "BatterySensor",
    "EnvironmentalChangeEvaluator",
    "EnvironmentalEventBuffer",
    "IdleTimeSensor",
    "NetworkConnectivitySensor",
    "Sensor",
    "SensorMonitor",
    "SensorReading",
    "SensorUnavailableError",
    "SystemLoadSensor",
]
