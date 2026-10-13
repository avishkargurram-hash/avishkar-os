"""Real local STT tests. FasterWhisperSTT genuinely runs CTranslate2
Whisper inference on this machine. test_real_round_trip_transcription
synthesizes real audio with Pyttsx3TTS (no live microphone involved)
and feeds it to a real faster-whisper model -- an actual, non-mocked,
non-fabricated speech pipeline test. The "tiny" model is used to keep
this fast; it is downloaded from Hugging Face on first run and cached
locally after. If no network is available to fetch it the first time,
the test skips with an explicit reason rather than failing the whole
suite or fabricating a pass.
"""

import unittest

import numpy as np

from avishkar_layla.voice.errors import NoSpeechDetectedError, STTProviderNotConfiguredError, TranscriptionError
from avishkar_layla.voice.stt import FasterWhisperSTT, STTResult
from avishkar_layla.voice.tts import Pyttsx3TTS


class TestFasterWhisperSTTReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stt = FasterWhisperSTT(model_size="tiny.en", device="cpu", compute_type="int8")
        try:
            cls.stt._ensure_model()
        except (STTProviderNotConfiguredError, TranscriptionError) as exc:
            raise unittest.SkipTest(f"faster-whisper 'tiny.en' model unavailable in this environment: {exc}")

    def test_empty_audio_raises_no_speech_detected(self):
        with self.assertRaises(NoSpeechDetectedError):
            self.stt.transcribe(np.zeros(0, dtype=np.float32), 16000)

    def test_real_round_trip_transcription(self):
        tts = Pyttsx3TTS(rate=150)
        tts_result = tts.synthesize("Open the calendar and schedule a meeting.")

        stt_result = self.stt.transcribe(tts_result.audio, tts_result.sample_rate)

        self.assertIsInstance(stt_result, STTResult)
        self.assertEqual(stt_result.provider, "faster-whisper")
        self.assertGreater(len(stt_result.text), 0)
        self.assertGreaterEqual(stt_result.confidence, 0.0)
        self.assertLessEqual(stt_result.confidence, 1.0)
        # Fuzzy match -- real STT is not byte-perfect, so we check that
        # the dominant real words made it through, not exact equality.
        lowered = stt_result.text.lower()
        self.assertTrue(
            "calendar" in lowered or "meeting" in lowered or "schedule" in lowered,
            f"expected recognizable words in real transcript, got: {stt_result.text!r}",
        )

    def test_pure_silence_produces_empty_or_near_empty_transcript(self):
        silence = np.zeros(16000, dtype=np.float32)  # 1 second of true digital silence
        stt_result = self.stt.transcribe(silence, 16000)
        self.assertLessEqual(len(stt_result.text.strip()), 3)


if __name__ == "__main__":
    unittest.main()
