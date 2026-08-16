"""Errors for the environmental-awareness subsystem. See CONTRACT.md SS38."""

from __future__ import annotations

from ..errors import LaylaError


class SensorUnavailableError(LaylaError):
    """A sensor's real backing data source doesn't exist on this
    machine (no battery, wrong OS for this sensor's implementation) --
    raised rather than fabricating a reading.
    """
