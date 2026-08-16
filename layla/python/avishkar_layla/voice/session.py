"""VoiceSession -- orchestrates one continuous voice interaction:
Mic -> AudioCapture -> VAD -> STT -> Layla Brain -> TTS -> Speaker.
Mission Layla Directive D, Part I. See CONTRACT.md SS32.

Security boundary (Directive D Part I, verbatim requirement: "Voice
must enter through the same Layla security/decision architecture"):
every transcript that isn't a local stop/cancel phrase is handed to
`runtime.handle_event()` UNCHANGED -- the existing
ExecutiveRuntime.handle_event() pipeline (intent -> context -> risk
classification -> planning -> approval -> execution) is not
bypassed, duplicated, or shortcut here. VoiceSession never calls a
tool, executor, or capability directly; it only ever transcribes,
calls handle_event(), and speaks the result. The one deliberate local
exception is a stop/cancel phrase, handled entirely inside this
session (setting an interrupt flag / ending the turn) precisely
because it is not itself a new action request -- it is a control
signal over *this session's own playback*, and routing it through
planning would defeat its purpose as an immediate interrupt.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from typing import Any, Optional, Protocol, Sequence

import numpy as np

from .errors import NoSpeechDetectedError, TranscriptionError, TTSProviderError, VoiceSessionClosedError
from .stt import SpeechToTextProvider
from .tts import TextToSpeechProvider
from .vad import EnergyVAD, VoiceActivityDetector

DEFAULT_STOP_PHRASES = ("stop", "layla stop", "cancel", "cancel that", "never mind", "that's all", "nevermind")

_TERMINAL_RESPONSE_STATES = {
    "COMPLETED": lambda task: task.result or "Done.",
    "FAILED": lambda task: f"I couldn't complete that: {task.blocked_reason or 'an error occurred'}.",
    "CANCELLED": lambda task: "Okay, I've cancelled that.",
    "TIMEOUT": lambda task: "That took too long, so I stopped.",
    "BLOCKED": lambda task: f"I'm blocked: {task.blocked_reason or 'a conflict I could not resolve'}.",
    "REQUIRES_HUMAN": lambda task: "That needs your approval before I can continue.",
    "APPROVAL_PENDING": lambda task: "That needs your approval before I can continue.",
}


class FrameSource(Protocol):
    def read(self, timeout: float) -> Optional[np.ndarray]:
        ...


@dataclasses.dataclass(frozen=True)
class VoiceTurnResult:
    transcript: str
    stt_confidence: float
    stopped: bool
    task: Optional[Any]  # LaylaTask, kept as Any to avoid a hard import cycle with runtime.py
    spoken_response: str
    tts_provider: Optional[str] = None
    played: Optional[bool] = None  # None if no speaker configured, else True/False (interrupted)


class VoiceSessionRuntime(Protocol):
    def handle_event(self, input_text: str, *, session_id: Optional[str] = None) -> Any:
        ...


class VoiceSession:
    def __init__(
        self,
        *,
        runtime: VoiceSessionRuntime,
        stt: SpeechToTextProvider,
        tts: TextToSpeechProvider,
        vad: Optional[VoiceActivityDetector] = None,
        speaker: Optional[Any] = None,  # SpeakerSink -- kept Any to stay hardware-optional
        audit: Optional[Any] = None,  # AuditLogger
        session_id: Optional[str] = None,
        stop_phrases: Sequence[str] = DEFAULT_STOP_PHRASES,
        clock: Any = time.monotonic,
    ) -> None:
        self._runtime = runtime
        self._stt = stt
        self._tts = tts
        self._vad = vad or EnergyVAD()
        self._speaker = speaker
        self._audit = audit
        self._session_id = session_id
        self._stop_phrases = tuple(p.lower() for p in stop_phrases)
        self._clock = clock
        self._interrupt_event = threading.Event()
        self._closed = False

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    def _require_open(self) -> None:
        if self._closed:
            raise VoiceSessionClosedError(f"VoiceSession {self._session_id!r} was closed")

    def _record(self, event_type: str, payload: dict) -> None:
        if self._audit is not None:
            self._audit.record(event_type, payload, task_id=self._session_id)

    def _is_stop_command(self, transcript: str) -> bool:
        normalized = transcript.strip().lower().rstrip(".!?")
        return normalized in self._stop_phrases

    def request_stop(self) -> None:
        """Interrupts any in-progress playback (barge-in) and marks the
        next listen loop to end quickly. Safe to call from another
        thread (e.g. a push-to-talk key handler, or a separate VAD
        monitor watching for the user speaking over Layla).
        """
        self._interrupt_event.set()

    def clear_stop(self) -> None:
        self._interrupt_event.clear()

    # -- Capture -----------------------------------------------------

    def listen_for_utterance(
        self, frame_source: FrameSource, *, sample_rate: int = 16000, max_listen_seconds: float = 12.0,
        silence_timeout_seconds: float = 1.0, pre_roll_frames: int = 5,
    ) -> np.ndarray:
        """Real VAD-driven segmentation: reads frames from any
        FrameSource (a real MicrophoneFrameSource in production, or a
        deterministic fake in tests -- the algorithm itself doesn't
        know or care which) until speech is detected and then trails
        off, or raises NoSpeechDetectedError if max_listen_seconds
        elapses with no speech ever detected.
        """
        self._require_open()
        self._vad.reset()
        preroll: list = []
        frames: list = []
        triggered = False
        silence_start: Optional[float] = None
        start = self._clock()

        while True:
            now = self._clock()
            elapsed = now - start
            if elapsed >= max_listen_seconds:
                if not triggered:
                    raise NoSpeechDetectedError(
                        f"no speech detected within {max_listen_seconds}s"
                    )
                break

            remaining = max_listen_seconds - elapsed
            frame = frame_source.read(min(remaining, 0.5))
            if frame is None:
                continue

            is_speech = self._vad.is_speech(frame, sample_rate)
            if not triggered:
                preroll.append(frame)
                if len(preroll) > pre_roll_frames:
                    preroll.pop(0)
                if is_speech:
                    triggered = True
                    frames.extend(preroll)
                    frames.append(frame)
                    silence_start = None
            else:
                frames.append(frame)
                if is_speech:
                    silence_start = None
                else:
                    if silence_start is None:
                        silence_start = now
                    elif now - silence_start >= silence_timeout_seconds:
                        break

        audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        self._record("layla.voice.utterance_captured", {"frames": len(frames), "samples": int(audio.size)})
        return audio

    # -- Turn processing ----------------------------------------------

    def _synthesize_response_text(self, task: Any) -> str:
        formatter = _TERMINAL_RESPONSE_STATES.get(getattr(task, "state", None))
        if formatter is not None:
            return formatter(task)
        return "I'm working on it."

    def handle_utterance(self, audio: np.ndarray, sample_rate: int) -> VoiceTurnResult:
        """STT -> (stop-phrase check | handle_event) -> spoken response
        text. Never plays audio itself -- see run_turn() for the full
        listen+respond+speak cycle.
        """
        self._require_open()
        try:
            stt_result = self._stt.transcribe(audio, sample_rate)
        except NoSpeechDetectedError:
            self._record("layla.voice.no_speech", {})
            return VoiceTurnResult(
                transcript="", stt_confidence=0.0, stopped=False, task=None,
                spoken_response="I didn't catch that.",
            )
        except TranscriptionError as exc:
            self._record("layla.voice.stt_error", {"error": str(exc)})
            return VoiceTurnResult(
                transcript="", stt_confidence=0.0, stopped=False, task=None,
                spoken_response="Sorry, I had trouble understanding that.",
            )

        transcript = stt_result.text.strip()
        if not transcript:
            self._record("layla.voice.empty_transcript", {})
            return VoiceTurnResult(
                transcript="", stt_confidence=stt_result.confidence, stopped=False, task=None,
                spoken_response="I didn't catch that.",
            )

        if self._is_stop_command(transcript):
            self.request_stop()
            self._record("layla.voice.stopped", {"transcript": transcript})
            return VoiceTurnResult(
                transcript=transcript, stt_confidence=stt_result.confidence, stopped=True, task=None,
                spoken_response="Okay.",
            )

        self._record("layla.voice.transcript_routed", {"transcript": transcript, "confidence": stt_result.confidence})
        task = self._runtime.handle_event(transcript, session_id=self._session_id)
        spoken_response = self._synthesize_response_text(task)
        self._record("layla.voice.turn_completed", {"task_id": getattr(task, "id", None), "state": getattr(task, "state", None)})
        return VoiceTurnResult(
            transcript=transcript, stt_confidence=stt_result.confidence, stopped=False, task=task,
            spoken_response=spoken_response,
        )

    def speak(self, text: str) -> bool:
        """Synthesizes and (if a speaker is configured) plays `text`.
        Returns True if playback completed / no speaker configured,
        False if playback was interrupted (barge-in).
        """
        self._require_open()
        try:
            tts_result = self._tts.synthesize(text)
        except TTSProviderError as exc:
            self._record("layla.voice.tts_error", {"error": str(exc)})
            return True
        if self._speaker is None:
            return True
        return self._speaker.play(tts_result.audio, tts_result.sample_rate, interrupt_event=self._interrupt_event)

    def run_turn(
        self, frame_source: FrameSource, *, sample_rate: int = 16000, max_listen_seconds: float = 12.0,
        silence_timeout_seconds: float = 1.0, speak: bool = True,
    ) -> VoiceTurnResult:
        """One full listen -> route -> respond cycle."""
        self._require_open()
        self.clear_stop()
        try:
            audio = self.listen_for_utterance(
                frame_source, sample_rate=sample_rate, max_listen_seconds=max_listen_seconds,
                silence_timeout_seconds=silence_timeout_seconds,
            )
        except NoSpeechDetectedError:
            return VoiceTurnResult(
                transcript="", stt_confidence=0.0, stopped=False, task=None,
                spoken_response="", played=None,
            )

        result = self.handle_utterance(audio, sample_rate)
        played: Optional[bool] = None
        if speak and result.spoken_response:
            played = self.speak(result.spoken_response)
        return dataclasses.replace(result, played=played)

    def close(self) -> None:
        self._closed = True
        self._record("layla.voice.session_closed", {})
