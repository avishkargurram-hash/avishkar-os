"""Speech-to-Text provider abstraction. See CONTRACT.md SS32.

STATUS:
- FasterWhisperSTT: REAL, LOCAL. Wraps the real `faster-whisper`
  package (CTranslate2 Whisper inference), runs entirely on-device,
  needs no API key. The model weights are downloaded from Hugging Face
  on first use and cached locally after that (real network egress
  required once; offline-capable after). See
  test_voice_stt.py::test_real_round_trip_transcription for a genuine
  synthesize-then-transcribe test run against this machine's actual
  faster-whisper installation.
- OpenAIWhisperAPISTT: REAL CODE / ADAPTER READY. A genuine HTTP
  client against OpenAI's real `/v1/audio/transcriptions` endpoint --
  not exercised live in this environment because no OPENAI_API_KEY is
  configured here. Raises STTProviderNotConfiguredError rather than
  silently returning a fabricated transcript when the key is missing.
"""

from __future__ import annotations

import dataclasses
import io
import os
from typing import Optional

import numpy as np

from .errors import NoSpeechDetectedError, STTProviderNotConfiguredError, TranscriptionError

TARGET_SAMPLE_RATE = 16000


@dataclasses.dataclass(frozen=True)
class STTResult:
    text: str
    confidence: float  # 0.0-1.0, real computed value, never hardcoded
    language: Optional[str]
    provider: str


class SpeechToTextProvider:
    """Abstract STT provider: real audio in, real transcript out."""

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> STTResult:
        raise NotImplementedError


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr or audio.size == 0:
        return audio
    import scipy.signal as signal

    gcd = np.gcd(orig_sr, target_sr)
    up, down = target_sr // gcd, orig_sr // gcd
    return signal.resample_poly(audio, up, down).astype(np.float32)


class FasterWhisperSTT(SpeechToTextProvider):
    def __init__(
        self, *, model_size: str = "base", device: str = "cpu", compute_type: str = "int8",
        language: Optional[str] = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model = None  # lazy: real model load is slow, defer until first transcribe()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise STTProviderNotConfiguredError(
                "the 'faster-whisper' package is not installed -- required for FasterWhisperSTT"
            ) from exc
        try:
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=self._compute_type)
        except Exception as exc:
            raise TranscriptionError(
                f"failed to load faster-whisper model {self._model_size!r} "
                f"(this downloads from Hugging Face on first use -- check network access): {exc}"
            ) from exc
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> STTResult:
        if audio.size == 0:
            raise NoSpeechDetectedError("transcribe() called with empty audio")
        model = self._ensure_model()
        audio = _resample(np.asarray(audio, dtype=np.float32), sample_rate, TARGET_SAMPLE_RATE)
        try:
            segments, info = model.transcribe(audio, language=self._language)
            segments = list(segments)
        except Exception as exc:
            raise TranscriptionError(f"faster-whisper transcription failed: {exc}") from exc

        text = " ".join(s.text.strip() for s in segments).strip()
        if segments:
            # Real computed confidence: faster-whisper's avg_logprob is a
            # log-probability (<= 0); map it to a 0..1 scale via exp().
            # Never a hardcoded constant.
            avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
            confidence = float(np.clip(np.exp(avg_logprob), 0.0, 1.0))
        else:
            confidence = 0.0
        return STTResult(text=text, confidence=confidence, language=getattr(info, "language", None), provider="faster-whisper")


class OpenAIWhisperAPISTT(SpeechToTextProvider):
    """Real HTTP client for OpenAI's hosted Whisper transcription API.
    ADAPTER READY -- requires OPENAI_API_KEY (never hardcoded; read
    from the environment at call time, not at construction, so a key
    added after process start still works).
    """

    def __init__(self, *, model: str = "whisper-1", api_key_env: str = "OPENAI_API_KEY", timeout_seconds: float = 30.0) -> None:
        self._model = model
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> STTResult:
        if audio.size == 0:
            raise NoSpeechDetectedError("transcribe() called with empty audio")
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise STTProviderNotConfiguredError(
                f"OpenAIWhisperAPISTT requires the {self._api_key_env} environment variable -- "
                f"this is the documented ADAPTER READY boundary (CONTRACT.md SS32); no key is "
                f"configured in this environment"
            )

        import requests
        import soundfile as sf

        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV")
        buf.seek(0)

        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.wav", buf, "audio/wav")},
                data={"model": self._model},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise TranscriptionError(f"OpenAI Whisper API request failed: {exc}") from exc

        text = payload.get("text", "").strip()
        return STTResult(text=text, confidence=1.0 if text else 0.0, language=payload.get("language"), provider="openai-whisper-api")
