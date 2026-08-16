"""Real local audio device discovery, capture, and playback. See
CONTRACT.md SS32.

STATUS: REAL, LOCAL, HARDWARE-BACKED. Built on `sounddevice`
(PortAudio) -- genuine microphone capture and speaker playback on
whatever machine Layla is running on, no cloud service or credential
involved. This is the ONLY file in the voice subsystem that opens a
real audio device, and MicrophoneFrameSource is never instantiated by
the automated test suite: opening a live microphone non-interactively
during an autonomous test run would record whatever is actually being
said in the room, which this codebase treats as a real-world action
requiring the same "never do this without a clear, deliberate trigger"
discipline as any other physical-world capability (Directive D Part
VI: "do NOT poll continuously"; here, "do NOT record without an
explicit session"). Device *enumeration* (list_input_devices /
list_output_devices) does not record anything and is exercised for
real in test_voice_audio_io.py -- see that file for what actually ran
on this machine.
"""

from __future__ import annotations

import dataclasses
import queue
from typing import Optional, Tuple

import numpy as np

from .errors import AudioDeviceError

DEFAULT_SAMPLE_RATE = 16000  # Hz -- matches faster-whisper's native input rate
DEFAULT_CHANNELS = 1
DEFAULT_FRAME_MS = 30


@dataclasses.dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float


def _query_devices():
    try:
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover -- sounddevice is a declared dependency
        raise AudioDeviceError(
            "the 'sounddevice' package is not installed -- required for real audio capture/playback"
        ) from exc
    try:
        return sd, sd.query_devices()
    except Exception as exc:  # pragma: no cover -- PortAudio init failure (no audio subsystem at all)
        raise AudioDeviceError(f"failed to query audio devices: {exc}") from exc


def list_input_devices() -> Tuple[AudioDevice, ...]:
    """Real device enumeration -- no recording. Safe to call from
    automated tests and from a UI's device-picker.
    """
    _sd, devices = _query_devices()
    return tuple(
        AudioDevice(
            index=i, name=d["name"], max_input_channels=d["max_input_channels"],
            max_output_channels=d["max_output_channels"], default_sample_rate=d["default_samplerate"],
        )
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    )


def list_output_devices() -> Tuple[AudioDevice, ...]:
    _sd, devices = _query_devices()
    return tuple(
        AudioDevice(
            index=i, name=d["name"], max_input_channels=d["max_input_channels"],
            max_output_channels=d["max_output_channels"], default_sample_rate=d["default_samplerate"],
        )
        for i, d in enumerate(devices)
        if d["max_output_channels"] > 0
    )


class MicrophoneFrameSource:
    """A real, live microphone exposed as an iterator of mono float32
    frames at `sample_rate`. Opens a genuine `sounddevice.InputStream`
    on construction/`__enter__` and closes it on `__exit__` -- never
    opened implicitly; a caller (VoiceSession, in production wiring)
    must explicitly construct one. Raises AudioDeviceError immediately
    if no usable input device exists, rather than yielding silence.
    """

    def __init__(
        self, *, device: Optional[int] = None, sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_ms: int = DEFAULT_FRAME_MS,
    ) -> None:
        inputs = list_input_devices()
        if device is None and not inputs:
            raise AudioDeviceError("no input (microphone) audio device is available on this machine")
        if device is not None and not any(d.index == device for d in inputs):
            raise AudioDeviceError(f"requested input device index {device} is not a valid input device")
        self._device = device
        self._sample_rate = sample_rate
        self._frame_samples = int(sample_rate * frame_ms / 1000)
        self._stream = None
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()

    def __enter__(self) -> "MicrophoneFrameSource":
        import sounddevice as sd

        def _callback(indata, frame_count, time_info, status) -> None:  # pragma: no cover -- PortAudio callback thread
            self._queue.put(indata[:, 0].copy() if indata.ndim > 1 else indata.copy())

        try:
            self._stream = sd.InputStream(
                device=self._device, channels=1, samplerate=self._sample_rate,
                blocksize=self._frame_samples, dtype="float32", callback=_callback,
            )
            self._stream.start()
        except Exception as exc:
            raise AudioDeviceError(f"failed to open microphone stream: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read(self, timeout: float) -> Optional[np.ndarray]:
        """Blocks for up to `timeout` seconds for the next real frame.
        Returns None on timeout (caller decides what that means).
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


class SpeakerSink:
    """Real local speaker playback via `sounddevice.play()`. Supports
    early interruption (barge-in) by polling an `interrupt_event`
    between chunks rather than blocking on the whole clip at once.
    """

    def __init__(self, *, device: Optional[int] = None, chunk_seconds: float = 0.25) -> None:
        outputs = list_output_devices()
        if device is None and not outputs:
            raise AudioDeviceError("no output (speaker) audio device is available on this machine")
        if device is not None and not any(d.index == device for d in outputs):
            raise AudioDeviceError(f"requested output device index {device} is not a valid output device")
        self._device = device
        self._chunk_seconds = chunk_seconds

    def play(self, audio: np.ndarray, sample_rate: int, *, interrupt_event=None) -> bool:
        """Plays `audio` in chunks. Returns True if playback completed,
        False if it was interrupted early via interrupt_event. Real
        hardware playback -- like MicrophoneFrameSource, never invoked
        by the automated test suite (see test_voice_audio_io.py).
        """
        import sounddevice as sd

        chunk_samples = max(1, int(sample_rate * self._chunk_seconds))
        for start in range(0, len(audio), chunk_samples):
            if interrupt_event is not None and interrupt_event.is_set():
                sd.stop()
                return False
            chunk = audio[start:start + chunk_samples]
            sd.play(chunk, sample_rate, device=self._device)
            sd.wait()
        return True
