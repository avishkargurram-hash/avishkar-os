"""Communication channels for Layla. See CONTRACT.md SS12/SS27/SS37.

A channel is an avishkar_integration.ProtocolAdapter (Phase 4), never
a parallel "channel" abstraction. Routing across multiple channels is
avishkar_integration.UniversalToolRegistry's job (one registry, many
registered adapters) -- Layla does not build a second router.

Each adapter's `transport=` is injectable (the same DI seam
RESTAdapter uses instead of a live network call); Directive D Part V
added a REAL transport implementation alongside each adapter
(`SMTPEmailTransport`, `WhatsAppCloudAPITransport`,
`TelegramBotAPITransport`, `SlackWebAPITransport`,
`DiscordBotAPITransport`, `TwilioSMSTransport`) -- genuine HTTP/SMTP
clients, real credentials read from environment variables, never
hardcoded. None has a live external account configured in this
environment; each is ADAPTER READY, not a fabricated live integration.
See README.md Communication Channels section for the GREEN/YELLOW
breakdown per channel.
"""

from .discord_adapter import DiscordBotAPITransport, DiscordChannelAdapter
from .email_adapter import EmailChannelAdapter, SMTPEmailTransport
from .slack_adapter import SlackChannelAdapter, SlackWebAPITransport
from .sms_adapter import SMSChannelAdapter, TwilioSMSTransport
from .telegram_adapter import TelegramBotAPITransport, TelegramChannelAdapter
from .whatsapp_adapter import WhatsAppChannelAdapter, WhatsAppCloudAPITransport

__all__ = [
    "DiscordBotAPITransport",
    "DiscordChannelAdapter",
    "EmailChannelAdapter",
    "SlackChannelAdapter",
    "SlackWebAPITransport",
    "SMSChannelAdapter",
    "SMTPEmailTransport",
    "TelegramBotAPITransport",
    "TelegramChannelAdapter",
    "TwilioSMSTransport",
    "WhatsAppChannelAdapter",
    "WhatsAppCloudAPITransport",
]
