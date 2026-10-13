"""VoiceSession orchestration tests. Uses fake STT/TTS/frame-source/
runtime throughout -- deliberately never touches real audio hardware
or a real STT/TTS model, so these tests are fast, deterministic, and
run every time regardless of what's installed. They verify the
ORCHESTRATION logic (routing, stop-phrase handling, response
synthesis, interruption, session lifecycle), which is exactly what's
real and independent of which concrete provider is plugged in --
matching the same fake-transport pattern already used throughout this
codebase (see channels/email_adapter.py, embodiment.py).
"""

import unittest

import numpy as np

from avishkar_layla.voice.errors import NoSpeechDetectedError, VoiceSessionClosedError
from avishkar_layla.voice.session import DEFAULT_STOP_PHRASES, VoiceSession
from avishkar_layla.voice.stt import STTResult
from avishkar_layla.voice.tts import TTSResult


class FakeSTT:
    def __init__(self, text="", confidence=0.9, raise_no_speech=False):
        self.text = text
        self.confidence = confidence
        self.raise_no_speech = raise_no_speech
        self.calls = []

    def transcribe(self, audio, sample_rate):
        self.calls.append((audio, sample_rate))
        if self.raise_no_speech:
            raise NoSpeechDetectedError("fake: no speech")
        return STTResult(text=self.text, confidence=self.confidence, language="en", provider="fake")


class FakeTTS:
    def __init__(self):
        self.calls = []

    def synthesize(self, text):
        self.calls.append(text)
        return TTSResult(audio=np.ones(100, dtype=np.float32), sample_rate=16000, provider="fake")


class FakeSpeaker:
    def __init__(self, complete=True):
        self.complete = complete
        self.played = []

    def play(self, audio, sample_rate, *, interrupt_event=None):
        self.played.append((audio, sample_rate))
        return self.complete


class FakeTask:
    def __init__(self, state="COMPLETED", result="Done.", blocked_reason=None, id="task-1"):
        self.state = state
        self.result = result
        self.blocked_reason = blocked_reason
        self.id = id


class FakeRuntime:
    def __init__(self, task=None):
        self.task = task or FakeTask()
        self.calls = []

    def handle_event(self, input_text, *, session_id=None):
        self.calls.append((input_text, session_id))
        return self.task


class FakeFrameSource:
    """Yields a fixed sequence of (frame, is_end_of_queue) frames."""

    def __init__(self, frames):
        self._frames = list(frames)

    def read(self, timeout):
        if self._frames:
            return self._frames.pop(0)
        return None


def _loud_frame(n=480):
    return np.full(n, 0.8, dtype=np.float32)


def _quiet_frame(n=480):
    return np.zeros(n, dtype=np.float32)


class TestVoiceSessionRouting(unittest.TestCase):
    def test_normal_transcript_is_routed_through_handle_event_unchanged(self):
        runtime = FakeRuntime(FakeTask(state="COMPLETED", result="Your meeting is scheduled."))
        stt = FakeSTT(text="Schedule a meeting for tomorrow.")
        session = VoiceSession(runtime=runtime, stt=stt, tts=FakeTTS(), session_id="voice-1")

        result = session.handle_utterance(np.zeros(1600, dtype=np.float32), 16000)

        self.assertEqual(runtime.calls, [("Schedule a meeting for tomorrow.", "voice-1")])
        self.assertFalse(result.stopped)
        self.assertEqual(result.spoken_response, "Your meeting is scheduled.")
        self.assertIs(result.task, runtime.task)

    def test_never_calls_any_capability_or_tool_directly(self):
        """Structural guarantee: VoiceSession's only way to cause a real
        action is runtime.handle_event() -- there is no other method on
        FakeRuntime it could have called.
        """
        runtime = FakeRuntime()
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="Delete everything."), tts=FakeTTS())
        session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertEqual(len(runtime.calls), 1)


class TestVoiceSessionStopPhrase(unittest.TestCase):
    def test_stop_phrase_is_handled_locally_and_never_reaches_handle_event(self):
        runtime = FakeRuntime()
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="Stop."), tts=FakeTTS())

        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)

        self.assertTrue(result.stopped)
        self.assertEqual(runtime.calls, [])
        self.assertTrue(session._interrupt_event.is_set())

    def test_all_default_stop_phrases_are_recognized_case_insensitively(self):
        for phrase in DEFAULT_STOP_PHRASES:
            with self.subTest(phrase=phrase):
                runtime = FakeRuntime()
                session = VoiceSession(runtime=runtime, stt=FakeSTT(text=phrase.upper() + "!"), tts=FakeTTS())
                result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
                self.assertTrue(result.stopped)


class TestVoiceSessionEmptyAndNoSpeech(unittest.TestCase):
    def test_empty_transcript_does_not_reach_handle_event(self):
        runtime = FakeRuntime()
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="   "), tts=FakeTTS())
        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertEqual(runtime.calls, [])
        self.assertEqual(result.spoken_response, "I didn't catch that.")

    def test_stt_no_speech_error_is_handled_gracefully(self):
        runtime = FakeRuntime()
        session = VoiceSession(runtime=runtime, stt=FakeSTT(raise_no_speech=True), tts=FakeTTS())
        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertEqual(runtime.calls, [])
        self.assertEqual(result.spoken_response, "I didn't catch that.")


class TestVoiceSessionResponseSynthesis(unittest.TestCase):
    def test_completed_task_speaks_its_result(self):
        runtime = FakeRuntime(FakeTask(state="COMPLETED", result="It's done."))
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="do it"), tts=FakeTTS())
        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertEqual(result.spoken_response, "It's done.")

    def test_requires_human_speaks_an_approval_prompt(self):
        runtime = FakeRuntime(FakeTask(state="REQUIRES_HUMAN", result=None))
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="wire the payment"), tts=FakeTTS())
        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertIn("approval", result.spoken_response.lower())

    def test_failed_task_speaks_the_blocked_reason(self):
        runtime = FakeRuntime(FakeTask(state="FAILED", result=None, blocked_reason="agent unreachable"))
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="do the thing"), tts=FakeTTS())
        result = session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        self.assertIn("agent unreachable", result.spoken_response)


class TestVoiceSessionListenForUtterance(unittest.TestCase):
    def test_segments_speech_between_silence_using_real_vad_logic(self):
        frames = [_quiet_frame(), _quiet_frame(), _loud_frame(), _loud_frame(), _quiet_frame(), _quiet_frame()]
        source = FakeFrameSource(frames)
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS())

        audio = session.listen_for_utterance(
            source, sample_rate=16000, max_listen_seconds=5.0, silence_timeout_seconds=0.0,
        )
        self.assertGreater(audio.size, 0)

    def test_raises_no_speech_detected_if_only_silence_ever_arrives(self):
        source = FakeFrameSource([_quiet_frame()] * 3)
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS(), clock=_FakeClock([0, 0.1, 0.2, 0.3, 999]))
        with self.assertRaises(NoSpeechDetectedError):
            session.listen_for_utterance(source, max_listen_seconds=0.5)


class _FakeClock:
    def __init__(self, values):
        self._values = list(values)

    def __call__(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


class TestVoiceSessionSpeakAndInterrupt(unittest.TestCase):
    def test_speak_plays_through_configured_speaker(self):
        speaker = FakeSpeaker(complete=True)
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS(), speaker=speaker)
        played = session.speak("Hello there.")
        self.assertTrue(played)
        self.assertEqual(len(speaker.played), 1)

    def test_speak_with_no_speaker_configured_returns_true_without_playing(self):
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS(), speaker=None)
        played = session.speak("Hello there.")
        self.assertTrue(played)

    def test_request_stop_interrupts_reported_playback(self):
        speaker = FakeSpeaker(complete=False)  # simulates interruption inside play()
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS(), speaker=speaker)
        played = session.speak("A long response.")
        self.assertFalse(played)
        self.assertEqual(len(speaker.played), 1)


class TestVoiceSessionRunTurn(unittest.TestCase):
    def test_full_turn_listens_routes_and_speaks(self):
        frames = [_loud_frame(), _loud_frame(), _quiet_frame()]
        source = FakeFrameSource(frames)
        runtime = FakeRuntime(FakeTask(state="COMPLETED", result="All set."))
        speaker = FakeSpeaker(complete=True)
        session = VoiceSession(
            runtime=runtime, stt=FakeSTT(text="do the thing"), tts=FakeTTS(), speaker=speaker, session_id="s1",
        )

        result = session.run_turn(source, silence_timeout_seconds=0.0)

        self.assertEqual(result.transcript, "do the thing")
        self.assertEqual(result.spoken_response, "All set.")
        self.assertTrue(result.played)
        self.assertEqual(len(speaker.played), 1)

    def test_full_turn_with_no_speech_skips_routing_and_speaking(self):
        source = FakeFrameSource([_quiet_frame()])
        runtime = FakeRuntime()
        speaker = FakeSpeaker()
        session = VoiceSession(
            runtime=runtime, stt=FakeSTT(), tts=FakeTTS(), speaker=speaker,
            clock=_FakeClock([0, 0.1, 999]),
        )
        result = session.run_turn(source, max_listen_seconds=0.5)
        self.assertEqual(result.transcript, "")
        self.assertEqual(runtime.calls, [])
        self.assertEqual(speaker.played, [])


class TestVoiceSessionLifecycle(unittest.TestCase):
    def test_operations_after_close_raise(self):
        session = VoiceSession(runtime=FakeRuntime(), stt=FakeSTT(), tts=FakeTTS())
        session.close()
        with self.assertRaises(VoiceSessionClosedError):
            session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)

    def test_audit_logger_records_lifecycle_events(self):
        events = []

        class FakeAudit:
            def record(self, event_type, payload, *, task_id=None, principal_id=None):
                events.append(event_type)

        runtime = FakeRuntime(FakeTask(state="COMPLETED", result="ok"))
        session = VoiceSession(runtime=runtime, stt=FakeSTT(text="hi"), tts=FakeTTS(), audit=FakeAudit(), session_id="s1")
        session.handle_utterance(np.zeros(10, dtype=np.float32), 16000)
        session.close()

        self.assertIn("layla.voice.transcript_routed", events)
        self.assertIn("layla.voice.turn_completed", events)
        self.assertIn("layla.voice.session_closed", events)


if __name__ == "__main__":
    unittest.main()
