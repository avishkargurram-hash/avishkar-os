"""Communication channels for Layla. See CONTRACT.md SS12.

A channel is an avishkar_integration.ProtocolAdapter (Phase 4), never
a parallel "channel" abstraction -- see channels/email_adapter.py for
the one shipped, ADAPTER READY implementation.
"""

from .email_adapter import EmailChannelAdapter

__all__ = ["EmailChannelAdapter"]
