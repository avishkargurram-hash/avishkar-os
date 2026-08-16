"""Errors for the voice subsystem. See CONTRACT.md SS32."""

from __future__ import annotations

from ..errors import LaylaError


class AudioDeviceError(LaylaError):
    """No usable input/output audio device was found, or the configured
    device could not be opened. Raised instead of silently falling
    back to synthetic audio.
    """


class NoSpeechDetectedError(LaylaError):
    """A capture loop's VAD never detected speech before
    max_listen_seconds elapsed -- a normal, expected outcome (silence),
    not a hardware failure.
    """


class TranscriptionError(LaylaError):
    """An STT provider was given real, non-empty audio but failed to
    produce a transcript (model error, malformed audio, provider
    outage). Distinct from NoSpeechDetectedError.
    """


class STTProviderNotConfiguredError(LaylaError):
    """A cloud STT provider was invoked without its required credential
    or dependency -- the documented ADAPTER READY boundary.
    """


class TTSProviderError(LaylaError):
    """A TTS provider failed to synthesize or play back speech."""


class VoiceSessionClosedError(LaylaError):
    """An operation was attempted on a VoiceSession after close()."""
