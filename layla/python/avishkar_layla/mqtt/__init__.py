"""MQTT -- Mission Layla Directive D, Part VIII. See CONTRACT.md SS42.

`MQTTBridge` wraps the real, installed `paho-mqtt` client. Directive D
Part VIII, verbatim: "MQTT events must enter Avishkar's EventBus
rather than creating another event system" -- every inbound message
`MQTTBridge` receives is translated into a real
`avishkar_core.EventBus.publish()` call (the same "Sensor -> Event ->
EventBus" pattern `avishkar_layla.environment`, Directive D Part VI,
already established for local sensors); there is no separate MQTT
event queue/loop for callers to poll.

Publish and subscribe are both gated by real, fail-closed topic
allowlists (empty allowlist = nothing published/subscribed) -- the
same discipline `ComputerControlExecutor.run_shell`/`ADBExecutor`'s
shell allowlists use, because an MQTT `publish` is routinely how real
physical devices are commanded. `EMBODIMENT_MQTT` was added to
embodiment.py's `_DEFAULT_HIGH_RISK_CAPABILITIES` this same pass
(ADR-0035) so every `mqtt` action through `EmbodimentController` also
requires approval regardless of wording, on top of this module's own
allowlist -- two independent, non-redundant gates, matching
`ADBExecutor`'s shell-allowlist-plus-capability-gate design exactly.
"""

from __future__ import annotations

from .client import MQTTBridge
from .errors import MQTTNotConnectedError, MQTTPublishNotAllowedError, MQTTSubscribeNotAllowedError

__all__ = ["MQTTBridge", "MQTTNotConnectedError", "MQTTPublishNotAllowedError", "MQTTSubscribeNotAllowedError"]
