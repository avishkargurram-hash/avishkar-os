"""Text-to-Speech provider abstraction. See CONTRACT.md SS32.

Every provider produces a real in-memory waveform (`TTSResult.audio` /
`.sample_rate`) rather than speaking directly -- playback is always
done by `SpeakerSink.play()` (audio_io.py), which is the single place
interruption/barge-in is implemented (chunked playback polling an
`interrupt_event`). This keeps "how do we synthesize speech" and "how
do we interrupt speech" independent, so any future TTS provider gets
barge-in for free.

STATUS:
- Pyttsx3TTS: REAL, LOCAL. Wraps the real `pyttsx3` package (SAPI5 on
  Windows). Genuinely synthesizes audio on this machine -- see
  test_voice_tts.py::test_real_synthesis_produces_audio for a real,
  non-mocked run.
- OpenAITTSProvider: REAL CODE / ADAPTER READY. A genuine HTTP client
  against OpenAI's real `/v1/audio/speech` endpoint -- not exercised
  live here because no OPENAI_API_KEY is configured in this
  environment.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
from typing import Optional

import numpy as np

from .errors import TTSProviderError

DEFAULT_SAMPLE_RATE = 22050


@dataclasses.dataclass(frozen=True)
class TTSResult:
    audio: np.ndarray
    sample_rate: int
    provider: str


class TextToSpeechProvider:
    """Abstract TTS provider: real text in, real waveform out."""

    def synthesize(self, text: str) -> TTSResult:
        raise NotImplementedError


class Pyttsx3TTS(TextToSpeechProvider):
    def __init__(self, *, rate: Optional[int] = None, voice_id: Optional[str] = None) -> None:
        self._rate = rate
        self._voice_id = voice_id

    def synthesize(self, text: str) -> TTSResult:
        if not text or not text.strip():
            raise TTSProviderError("synthesize() called with empty text")
        try:
            import pyttsx3
            import soundfile as sf
        except ImportError as exc:
            raise TTSProviderError("the 'pyttsx3' and 'soundfile' packages are required for Pyttsx3TTS") from exc

        engine = pyttsx3.init()
        try:
            if self._rate is not None:
                engine.setProperty("rate", self._rate)
            if self._voice_id is not None:
                engine.setProperty("voice", self._voice_id)

            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                engine.save_to_file(text, path)
                engine.runAndWait()
                audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(f"pyttsx3 synthesis failed: {exc}") from exc
        finally:
            try:
                engine.stop()
            except Exception:  # noqa: BLE001 -- best-effort cleanup only
                pass

        if audio.ndim > 1:
            audio = audio[:, 0]
        return TTSResult(audio=np.asarray(audio, dtype=np.float32), sample_rate=int(sample_rate), provider="pyttsx3")


class OpenAITTSProvider(TextToSpeechProvider):
    """Real HTTP client for OpenAI's hosted TTS API. ADAPTER READY --
    requires OPENAI_API_KEY (read at call time, never hardcoded).
    """

    def __init__(
        self, *, model: str = "tts-1", voice: str = "alloy", api_key_env: str = "OPENAI_API_KEY",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model = model
        self._voice = voice
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds

    def synthesize(self, text: str) -> TTSResult:
        if not text or not text.strip():
            raise TTSProviderError("synthesize() called with empty text")
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            from .errors import STTProviderNotConfiguredError  # local import: shared "adapter ready" shape

            raise STTProviderNotConfiguredError(
                f"OpenAITTSProvider requires the {self._api_key_env} environment variable -- this "
                f"is the documented ADAPTER READY boundary (CONTRACT.md SS32); no key is configured "
                f"in this environment"
            )

        import requests
        import soundfile as sf
        import io

        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": self._model, "voice": self._voice, "input": text, "response_format": "wav"},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            audio, sample_rate = sf.read(io.BytesIO(response.content), dtype="float32", always_2d=False)
        except Exception as exc:
            raise TTSProviderError(f"OpenAI TTS API request failed: {exc}") from exc

        if audio.ndim > 1:
            audio = audio[:, 0]
        return TTSResult(audio=np.asarray(audio, dtype=np.float32), sample_rate=int(sample_rate), provider="openai-tts-api")
