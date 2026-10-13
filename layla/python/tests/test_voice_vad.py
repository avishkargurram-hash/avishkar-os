import unittest

import numpy as np

from avishkar_layla.voice.vad import EnergyVAD


def _silence(n=480):
    return np.zeros(n, dtype=np.float32)


def _tone(n=480, amplitude=0.5):
    t = np.linspace(0, 1, n, dtype=np.float32)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _noise(n=480, amplitude=0.001, seed=0):
    rng = np.random.default_rng(seed)
    return (amplitude * rng.standard_normal(n)).astype(np.float32)


class TestEnergyVAD(unittest.TestCase):
    def test_rejects_invalid_threshold_multiplier(self):
        with self.assertRaises(ValueError):
            EnergyVAD(threshold_multiplier=1.0)

    def test_loud_tone_is_classified_as_speech(self):
        vad = EnergyVAD()
        self.assertTrue(vad.is_speech(_tone(), 16000))

    def test_true_silence_is_not_classified_as_speech(self):
        vad = EnergyVAD()
        self.assertFalse(vad.is_speech(_silence(), 16000))

    def test_low_amplitude_noise_is_not_classified_as_speech(self):
        vad = EnergyVAD()
        self.assertFalse(vad.is_speech(_noise(), 16000))

    def test_calibrate_lets_a_louder_room_still_read_as_silence(self):
        # Without calibration, this room's ambient noise (rms ~0.01) sits
        # above the default initial threshold (0.003 * 2.5 = 0.0075) and
        # would misfire as "speech" on every frame -- the EMA in
        # is_speech() only adapts on frames it already believes are
        # silence, so it can never climb past its own starting threshold
        # unassisted. calibrate() is the real fix: seed the noise floor
        # directly from known-silence frames before classifying.
        vad = EnergyVAD()
        calibration_frames = [_noise(amplitude=0.01, seed=i) for i in range(10)]
        vad.calibrate(calibration_frames)

        self.assertFalse(vad.is_speech(_noise(amplitude=0.01, seed=999), 16000))
        # But a genuinely loud tone still clearly exceeds the calibrated floor.
        self.assertTrue(vad.is_speech(_tone(), 16000))

    def test_calibrate_with_no_frames_is_a_safe_no_op(self):
        vad = EnergyVAD(initial_noise_floor=0.003)
        vad.calibrate([])
        self.assertEqual(vad._noise_floor, 0.003)

    def test_ema_adapts_downward_when_a_calibrated_room_gets_quieter(self):
        vad = EnergyVAD()
        vad.calibrate([_noise(amplitude=0.01, seed=i) for i in range(10)])
        floor_before = vad._noise_floor
        for i in range(50):
            vad.is_speech(_silence(), 16000)
        self.assertLess(vad._noise_floor, floor_before)

    def test_reset_restores_initial_noise_floor(self):
        vad = EnergyVAD(initial_noise_floor=0.003)
        for i in range(20):
            vad.is_speech(_noise(amplitude=0.01, seed=i), 16000)
        vad.reset()
        self.assertEqual(vad._noise_floor, 0.003)

    def test_empty_frame_is_not_speech(self):
        vad = EnergyVAD()
        self.assertFalse(vad.is_speech(np.zeros(0, dtype=np.float32), 16000))


if __name__ == "__main__":
    unittest.main()
