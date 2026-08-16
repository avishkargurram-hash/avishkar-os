"""PerceptionEngine -- Mission Layla Parts 6/7/8/12/13/16 (Voice, Vision,
OCR, Spatial Intelligence, Environmental Awareness). See CONTRACT.md SS28.

STATUS: CONTRACT / INTEGRATION BOUNDARY ONLY. No microphone, camera,
screen-capture, or OCR backend is wired here -- this mission's own
forensic audit found real hardware-access code in GENESIS for exactly
these capabilities, but building a genuinely safe equivalent (real
audio/video pipeline, real consent/retention enforcement) is a
dedicated, multi-day effort, not compressible into this pass. Per the
directive's own explicit fallback: "create the correct production-
grade contract and integration boundary, document the limitation, test
everything that can genuinely be tested, and continue." This module is
that contract.

`PerceptionEngine` starts with zero registered capture sources -- there
is no default/fake camera or microphone. `observe(source)` on an
unregistered source raises `PerceptionSourceNotConfiguredError`, the
same ADAPTER READY pattern `channels/email_adapter.py` already
established for external transports. Every `PerceptionObservation`
carries `permissions_required` and `retention_policy` explicitly --
Mission Layla Part 6's own requirement that "every observation must
have source, timestamp, confidence, permissions, retention policy,"
and Part 6's explicit warning that "screen/camera observation must
NEVER silently become unrestricted surveillance": there is no
always-on capture loop anywhere in this module -- `observe()` is
call-and-return, never a background daemon.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from .errors import LaylaError

PERCEPTION_VOICE = "voice"
PERCEPTION_VISION = "vision"
PERCEPTION_OCR = "ocr"
PERCEPTION_SPATIAL = "spatial"
PERCEPTION_ENVIRONMENTAL = "environmental"

PERCEPTION_SOURCES = (
    PERCEPTION_VOICE, PERCEPTION_VISION, PERCEPTION_OCR, PERCEPTION_SPATIAL, PERCEPTION_ENVIRONMENTAL,
)

RETENTION_SESSION = "session"
RETENTION_PERSISTENT = "persistent"
RETENTION_EPHEMERAL = "ephemeral"


class PerceptionSourceNotConfiguredError(LaylaError):
    """observe() was called for a source with no registered capture
    function -- the documented ADAPTER READY boundary, exactly
    channels/email_adapter.py's "no real transport configured" pattern.
    """


class UnknownPerceptionSourceError(LaylaError):
    """register_capture()/observe() referenced a source outside
    PERCEPTION_SOURCES.
    """


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class PerceptionObservation:
    """Frozen-by-convention (not @dataclass(frozen=True) because
    `content` may itself be a real capture-library object we don't want
    to force into a hashable/comparable shape) -- every field Mission
    Layla Part 6 requires is here.
    """

    __slots__ = ("source", "observation_type", "content", "confidence", "timestamp", "permissions_required", "retention_policy")

    def __init__(
        self, source: str, observation_type: str, content: Any, *, confidence: float = 1.0,
        timestamp: Optional[str] = None, permissions_required: Sequence[str] = (), retention_policy: str = RETENTION_SESSION,
    ) -> None:
        self.source = source
        self.observation_type = observation_type
        self.content = content
        self.confidence = confidence
        self.timestamp = timestamp or _now()
        self.permissions_required = tuple(permissions_required)
        self.retention_policy = retention_policy

    def __repr__(self) -> str:
        return (
            f"PerceptionObservation(source={self.source!r}, observation_type={self.observation_type!r}, "
            f"confidence={self.confidence}, retention_policy={self.retention_policy!r})"
        )


PerceptionCapture = Callable[[], PerceptionObservation]


class PerceptionEngine:
    def __init__(self) -> None:
        self._captures: Dict[str, PerceptionCapture] = {}

    def register_capture(self, source: str, capture: PerceptionCapture) -> None:
        if source not in PERCEPTION_SOURCES:
            raise UnknownPerceptionSourceError(f"unknown perception source {source!r} -- expected one of {PERCEPTION_SOURCES}")
        self._captures[source] = capture

    def configured_sources(self) -> Tuple[str, ...]:
        return tuple(self._captures.keys())

    def observe(self, source: str) -> PerceptionObservation:
        if source not in PERCEPTION_SOURCES:
            raise UnknownPerceptionSourceError(f"unknown perception source {source!r} -- expected one of {PERCEPTION_SOURCES}")
        capture = self._captures.get(source)
        if capture is None:
            raise PerceptionSourceNotConfiguredError(
                f"perception source {source!r} has no real capture backend configured -- this is the "
                f"documented ADAPTER READY boundary (CONTRACT.md SS28): wire a real capture function "
                f"via register_capture() before observing this source in production."
            )
        return capture()

    def observe_all(self) -> Tuple[PerceptionObservation, ...]:
        """Only observes sources that are actually configured -- never
        raises for the unconfigured ones, so a partially-equipped
        deployment (e.g. vision but no voice) still works.
        """
        return tuple(self.observe(source) for source in self._captures)
