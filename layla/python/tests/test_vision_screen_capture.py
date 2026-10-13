"""capture_screen() tests. Real error-handling is tested via the
`_grab_fn` injection seam -- the LIVE screen is never opened by these
tests (see screen_capture.py's module docstring for why). This is the
same DI pattern voice/audio_io.py's real hardware wrappers use.
"""

import unittest

from avishkar_layla.vision.errors import ScreenCaptureError
from avishkar_layla.vision.screen_capture import capture_screen


class TestCaptureScreen(unittest.TestCase):
    def test_returns_whatever_the_grab_fn_returns(self):
        sentinel = object()
        result = capture_screen(_grab_fn=lambda region: sentinel)
        self.assertIs(result, sentinel)

    def test_region_is_passed_through_to_grab_fn(self):
        seen = {}

        def fake_grab(region):
            seen["region"] = region
            return None

        capture_screen(region=(0, 0, 100, 100), _grab_fn=fake_grab)
        self.assertEqual(seen["region"], (0, 0, 100, 100))

    def test_grab_failure_is_wrapped_in_screen_capture_error(self):
        def failing_grab(region):
            raise RuntimeError("no display attached")

        with self.assertRaises(ScreenCaptureError):
            capture_screen(_grab_fn=failing_grab)

    def test_missing_pillow_is_reported_clearly(self):
        def missing_pillow(region):
            raise ImportError("no module named PIL")

        with self.assertRaises(ScreenCaptureError) as ctx:
            capture_screen(_grab_fn=missing_pillow)
        self.assertIn("Pillow", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
