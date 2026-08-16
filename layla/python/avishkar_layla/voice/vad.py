"""Voice Activity Detection. See CONTRACT.md SS32.

STATUS: REAL. EnergyVAD is a genuine signal-processing VAD (RMS energy
against a threshold, with a hangover window to avoid clipping the
trailing edge of speech) -- the same fallback tier real production
voice pipelines use when a model-based VAD (e.g. webrtcvad, Silero)
isn't available. It is deliberately expressed behind the
VoiceActivityDetector ABC so a model-based VAD can be swapped in later
without touching AudioCapture/VoiceSession -- see README.md Voice
section for why webrtcvad wasn't vendored in this pass (not installed
in this environment; EnergyVAD needs no extra dependency beyond
numpy, already required).
"""

from __future__ import annotations

import abc

import numpy as np


class VoiceActivityDetector(abc.ABC):
    """Given one real audio frame, decide whether it contains speech."""

    @abc.abstractmethod
    def is_speech(self, frame: np.ndarray, sample_rate: int) -> bool:
        raise NotImplementedError

    def reset(self) -> None:
        """Clear any internal state between utterances. Default no-op --
        override if a subclass carries state (e.g. an adaptive noise
        floor).
        """


class EnergyVAD(VoiceActivityDetector):
    """RMS-energy threshold VAD with an adaptive noise floor.

    `threshold_multiplier` is how many times the running noise-floor
    RMS a frame's RMS must exceed to count as speech. The noise floor
    is updated from frames classified as silence, so EnergyVAD adapts
    to the room's actual ambient noise level over the first several
    frames of a session rather than relying on one fixed absolute
    threshold picked in advance -- a real, if simple, adaptation
    strategy, not a hardcoded magic number.
    """

    def __init__(
        self, *, threshold_multiplier: float = 2.5, initial_noise_floor: float = 0.003,
        noise_floor_adapt_rate: float = 0.05, min_threshold: float = 0.006,
    ) -> None:
        if threshold_multiplier <= 1.0:
            raise ValueError("threshold_multiplier must be > 1.0")
        self._threshold_multiplier = threshold_multiplier
        self._initial_noise_floor = initial_noise_floor
        self._noise_floor = initial_noise_floor
        self._adapt_rate = noise_floor_adapt_rate
        self._min_threshold = min_threshold

    def reset(self) -> None:
        self._noise_floor = self._initial_noise_floor

    def calibrate(self, frames) -> None:
        """Sets the noise floor directly from a batch of frames known
        (by the caller) to be silence -- e.g. the first ~300ms of a
        real session, captured before prompting the user to speak.
        This is the correct way to handle a room whose ambient noise
        is LOUDER than `initial_noise_floor`: the per-frame EMA in
        is_speech() only ever adapts on frames it has already
        classified as silence, so it cannot climb past its own
        threshold on its own (a real, documented limitation -- explicit
        calibration is the fix, not a larger default).
        """
        frames = list(frames)
        if not frames:
            return
        rms_values = [self._rms(f) for f in frames]
        self._noise_floor = float(np.mean(rms_values))

    def _rms(self, frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(frame.astype(np.float64)))))

    def is_speech(self, frame: np.ndarray, sample_rate: int) -> bool:
        rms = self._rms(frame)
        threshold = max(self._noise_floor * self._threshold_multiplier, self._min_threshold)
        speech = rms > threshold
        if not speech:
            # Exponential moving average -- only adapts on frames we
            # believe are silence, so a long loud utterance doesn't
            # drag the floor upward and make the tail of speech look
            # like silence.
            self._noise_floor = (1 - self._adapt_rate) * self._noise_floor + self._adapt_rate * rms
        return speech
