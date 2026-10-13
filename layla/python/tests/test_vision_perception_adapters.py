"""screen_capture_source()/screen_ocr_source() wiring tests. Real
PerceptionObservation shape, exercised against a monkeypatched
capture_screen/extract_text -- never the live screen (consistent with
every other vision/voice hardware test in this suite).
"""

import unittest
from unittest import mock

from avishkar_layla.perception import PERCEPTION_OCR, PERCEPTION_VISION, RETENTION_EPHEMERAL
from avishkar_layla.vision import perception_adapters
from avishkar_layla.vision.ocr import OCRResult, OCRWord
from avishkar_layla.vision.spatial import BoundingBox


class TestScreenCaptureSource(unittest.TestCase):
    def test_produces_a_vision_observation_with_the_real_image_as_content(self):
        sentinel_image = object()
        with mock.patch.object(perception_adapters, "capture_screen", return_value=sentinel_image):
            observation = perception_adapters.screen_capture_source()

        self.assertEqual(observation.source, PERCEPTION_VISION)
        self.assertEqual(observation.observation_type, "screen_capture")
        self.assertIs(observation.content, sentinel_image)
        self.assertEqual(observation.confidence, 1.0)
        self.assertEqual(observation.retention_policy, RETENTION_EPHEMERAL)
        self.assertIn("screen_capture", observation.permissions_required)


class TestScreenOCRSource(unittest.TestCase):
    def test_confidence_is_the_real_mean_of_word_confidences(self):
        words = (
            OCRWord(text="hello", confidence=0.8, box=BoundingBox(0, 0, 10, 10)),
            OCRWord(text="world", confidence=0.6, box=BoundingBox(20, 0, 30, 10)),
        )
        result = OCRResult(text="hello world", words=words)
        with mock.patch.object(perception_adapters, "capture_screen", return_value=object()), \
             mock.patch.object(perception_adapters, "extract_text", return_value=result):
            observation = perception_adapters.screen_ocr_source()

        self.assertEqual(observation.source, PERCEPTION_OCR)
        self.assertAlmostEqual(observation.confidence, 0.7)
        self.assertIs(observation.content, result)

    def test_no_words_gives_zero_confidence_not_a_fabricated_default(self):
        empty_result = OCRResult(text="", words=())
        with mock.patch.object(perception_adapters, "capture_screen", return_value=object()), \
             mock.patch.object(perception_adapters, "extract_text", return_value=empty_result):
            observation = perception_adapters.screen_ocr_source()

        self.assertEqual(observation.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
