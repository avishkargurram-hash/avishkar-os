"""Voice subsystem -- Mission Layla Directive D, Part I. See
CONTRACT.md SS32.

Mic -> AudioCapture -> VAD -> STT -> Layla Brain (ExecutiveRuntime,
unchanged) -> TTS -> Speaker. Every component here is provider-
abstracted (ABC + at least one real implementation) and injectable, so
VoiceSession's orchestration logic is testable without any live
hardware or credential, while the default wiring is genuinely real:

- VAD: EnergyVAD (numpy RMS-threshold with hangover) -- real, local,
  no model download.
- STT: FasterWhisperSTT (real, local, offline-capable after first
  model download, no API key) and OpenAIWhisperAPISTT (real HTTP
  client, ADAPTER READY -- requires OPENAI_API_KEY).
- TTS: Pyttsx3TTS (real, local, offline, SAPI5/NSSpeech/espeak
  depending on OS) and OpenAITTSProvider (real HTTP client, ADAPTER
  READY -- requires OPENAI_API_KEY).
- Audio I/O: MicrophoneFrameSource / SpeakerSink (real, sounddevice/
  PortAudio-backed) -- the ONLY files in this package that touch real
  hardware, and never invoked by the automated test suite (a live
  microphone is never opened non-interactively; see
  test_voice_audio_io.py).

STATUS: REAL for VAD, local STT/TTS, and orchestration. REAL CODE /
ADAPTER READY for the two cloud providers (no credential available in
this environment to test live). See README.md Voice section for the
GREEN/YELLOW breakdown.
"""

from __future__ import annotations

from .audio_io import (
    AudioDevice,
    MicrophoneFrameSource,
    SpeakerSink,
    list_input_devices,
    list_output_devices,
)
from .errors import (
    AudioDeviceError,
    NoSpeechDetectedError,
    STTProviderNotConfiguredError,
    TranscriptionError,
    TTSProviderError,
    VoiceSessionClosedError,
)
from .session import VoiceSession, VoiceTurnResult
from .stt import FasterWhisperSTT, OpenAIWhisperAPISTT, STTResult, SpeechToTextProvider
from .tts import OpenAITTSProvider, Pyttsx3TTS, TextToSpeechProvider, TTSResult
from .vad import EnergyVAD, VoiceActivityDetector

__all__ = [
    "AudioDevice",
    "AudioDeviceError",
    "EnergyVAD",
    "FasterWhisperSTT",
    "MicrophoneFrameSource",
    "NoSpeechDetectedError",
    "OpenAITTSProvider",
    "OpenAIWhisperAPISTT",
    "Pyttsx3TTS",
    "SpeakerSink",
    "SpeechToTextProvider",
    "STTProviderNotConfiguredError",
    "STTResult",
    "TextToSpeechProvider",
    "TranscriptionError",
    "TTSProviderError",
    "TTSResult",
    "VoiceActivityDetector",
    "VoiceSession",
    "VoiceSessionClosedError",
    "VoiceTurnResult",
    "list_input_devices",
    "list_output_devices",
]
