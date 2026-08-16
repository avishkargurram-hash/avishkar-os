"""Communication channels for Layla. See CONTRACT.md SS12/SS27.

A channel is an avishkar_integration.ProtocolAdapter (Phase 4), never
a parallel "channel" abstraction. Routing across multiple channels is
avishkar_integration.UniversalToolRegistry's job (one registry, many
registered adapters) -- Layla does not build a second router. See
channels/email_adapter.py and channels/whatsapp_adapter.py for the
two shipped, ADAPTER READY implementations (Mission Layla Part 9).
"""

from .email_adapter import EmailChannelAdapter
from .whatsapp_adapter import WhatsAppChannelAdapter

__all__ = ["EmailChannelAdapter", "WhatsAppChannelAdapter"]
