"""Real template-detection tests. detect_template() genuinely runs
cv2.matchTemplate against synthetically-generated numpy images (no
live screen/camera involved) -- a real, non-mocked test of the actual
computer-vision code path.
"""

import unittest

import numpy as np

from avishkar_layla.vision.detection import detect_template, is_opencv_available


def _textured_canvas(size=200, seed=0):
    # A uniform-value background makes cv2.TM_CCOEFF_NORMED degenerate
    # (undefined 0/0 normalization reads as a false-positive 1.0 match
    # against ANY flat template) -- real textured noise, like a real
    # screenshot, avoids that and is what genuinely exercises the
    # threshold/suppression logic.
    rng = np.random.default_rng(seed)
    return rng.integers(40, 60, (size, size), dtype=np.uint8)


def _needle(size=20, value=220):
    rng = np.random.default_rng(42)
    needle = rng.integers(200, 240, (size, size), dtype=np.uint8)
    return needle


def _haystack_with_needle_at(x, y, needle_size=20, canvas_size=200):
    canvas = _textured_canvas(canvas_size)
    needle = _needle(needle_size)
    canvas[y:y + needle_size, x:x + needle_size] = needle
    return canvas, needle


@unittest.skipUnless(is_opencv_available(), "opencv-python not available in this environment")
class TestDetectTemplateReal(unittest.TestCase):
    def test_finds_a_real_exact_match(self):
        haystack, needle = _haystack_with_needle_at(x=50, y=70)

        matches = detect_template(haystack, needle, threshold=0.9)

        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.box.x0, 50)
        self.assertEqual(match.box.y0, 70)
        self.assertGreater(match.confidence, 0.99)

    def test_no_match_below_threshold_returns_empty(self):
        haystack = np.random.default_rng(0).integers(0, 255, (200, 200), dtype=np.uint8)
        needle = np.random.default_rng(1).integers(0, 255, (20, 20), dtype=np.uint8)

        matches = detect_template(haystack, needle, threshold=0.95)
        self.assertEqual(matches, ())

    def test_needle_larger_than_haystack_returns_empty_not_an_error(self):
        haystack = np.zeros((10, 10), dtype=np.uint8)
        needle = np.zeros((50, 50), dtype=np.uint8)
        self.assertEqual(detect_template(haystack, needle), ())

    def test_finds_multiple_non_overlapping_matches(self):
        canvas = _textured_canvas(200, seed=7)
        needle = _needle(15)
        canvas[10:25, 10:25] = needle
        canvas[150:165, 150:165] = needle

        matches = detect_template(canvas, needle, threshold=0.9)

        self.assertEqual(len(matches), 2)
        found_positions = {(m.box.x0, m.box.y0) for m in matches}
        self.assertIn((10, 10), found_positions)
        self.assertIn((150, 150), found_positions)


if __name__ == "__main__":
    unittest.main()
