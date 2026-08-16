"""Real, local TTS tests. Pyttsx3TTS.synthesize() genuinely runs the
SAPI5 (Windows) engine on this machine and writes/reads a real WAV
file -- no live speaker output is triggered (that's SpeakerSink.play(),
never invoked here).
"""

import unittest

from avishkar_layla.voice.errors import TTSProviderError
from avishkar_layla.voice.tts import Pyttsx3TTS, TTSResult


class TestPyttsx3TTSReal(unittest.TestCase):
    def test_real_synthesis_produces_audio(self):
        tts = Pyttsx3TTS()
        result = tts.synthesize("Testing one two three.")
        self.assertIsInstance(result, TTSResult)
        self.assertEqual(result.provider, "pyttsx3")
        self.assertGreater(result.sample_rate, 0)
        self.assertGreater(result.audio.size, 0)
        duration_seconds = result.audio.size / result.sample_rate
        self.assertGreater(duration_seconds, 0.2)

    def test_empty_text_raises(self):
        tts = Pyttsx3TTS()
        with self.assertRaises(TTSProviderError):
            tts.synthesize("")

    def test_whitespace_only_text_raises(self):
        tts = Pyttsx3TTS()
        with self.assertRaises(TTSProviderError):
            tts.synthesize("   ")

    def test_longer_text_produces_longer_audio(self):
        tts = Pyttsx3TTS(rate=200)
        short = tts.synthesize("Hi.")
        long = tts.synthesize("This is a considerably longer sentence than the first one.")
        self.assertGreater(long.audio.size / long.sample_rate, short.audio.size / short.sample_rate)


if __name__ == "__main__":
    unittest.main()
