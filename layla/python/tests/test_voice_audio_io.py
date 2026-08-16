"""Real, non-invasive audio hardware tests. list_input_devices() /
list_output_devices() only enumerate -- they never open a stream or
record/play anything, so it's safe to run these for real in the
default test suite. Actually opening a live microphone or speaker is
deliberately never done here -- see audio_io.py's module docstring.
"""

import unittest

from avishkar_layla.voice.audio_io import (
    AudioDevice,
    MicrophoneFrameSource,
    SpeakerSink,
    list_input_devices,
    list_output_devices,
)
from avishkar_layla.voice.errors import AudioDeviceError


class TestDeviceEnumeration(unittest.TestCase):
    def test_list_input_devices_returns_real_devices_on_this_machine(self):
        devices = list_input_devices()
        self.assertIsInstance(devices, tuple)
        for d in devices:
            self.assertIsInstance(d, AudioDevice)
            self.assertGreater(d.max_input_channels, 0)

    def test_list_output_devices_returns_real_devices_on_this_machine(self):
        devices = list_output_devices()
        self.assertIsInstance(devices, tuple)
        for d in devices:
            self.assertIsInstance(d, AudioDevice)
            self.assertGreater(d.max_output_channels, 0)


class TestMicrophoneFrameSourceValidation(unittest.TestCase):
    """Construction-time validation only -- no stream is ever opened by
    these tests (that would require entering the context manager).
    """

    def test_invalid_device_index_raises_without_opening_a_stream(self):
        with self.assertRaises(AudioDeviceError):
            MicrophoneFrameSource(device=999999)

    def test_valid_default_device_constructs_cleanly_if_any_input_exists(self):
        if not list_input_devices():
            self.skipTest("no input device available on this machine")
        source = MicrophoneFrameSource()
        self.assertIsNotNone(source)


class TestSpeakerSinkValidation(unittest.TestCase):
    def test_invalid_device_index_raises(self):
        with self.assertRaises(AudioDeviceError):
            SpeakerSink(device=999999)

    def test_valid_default_device_constructs_cleanly_if_any_output_exists(self):
        if not list_output_devices():
            self.skipTest("no output device available on this machine")
        sink = SpeakerSink()
        self.assertIsNotNone(sink)


if __name__ == "__main__":
    unittest.main()
