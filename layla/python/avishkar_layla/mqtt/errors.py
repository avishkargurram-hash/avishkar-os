"""Errors for the MQTT bridge. See CONTRACT.md SS42."""

from __future__ import annotations

from ..errors import LaylaError


class MQTTNotConnectedError(LaylaError):
    """publish()/subscribe() was called before connect() succeeded."""


class MQTTPublishNotAllowedError(LaylaError):
    """A publish topic did not match this bridge's configured
    allowlist -- fail closed, no default allowlist.
    """


class MQTTSubscribeNotAllowedError(LaylaError):
    """A subscribe topic filter did not match this bridge's configured
    allowlist -- fail closed, no default allowlist.
    """
