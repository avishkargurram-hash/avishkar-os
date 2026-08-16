"""Wires real vision capture/analysis as `PerceptionCapture` callables
for `avishkar_layla.perception.PerceptionEngine.register_capture()`.
See CONTRACT.md SS33.

These are the only functions in the vision package meant to be
registered directly; everything else (screen_capture, ocr, spatial,
detection) is a lower-level building block a caller can also use
standalone (e.g. computer-control verification, Directive D Part III).
"""

from __future__ import annotations

from ..perception import RETENTION_EPHEMERAL, PERCEPTION_OCR, PERCEPTION_VISION, PerceptionObservation
from .ocr import extract_text
from .screen_capture import capture_screen


def screen_capture_source() -> PerceptionObservation:
    """Real screen capture as a PERCEPTION_VISION observation."""
    image = capture_screen()
    return PerceptionObservation(
        source=PERCEPTION_VISION, observation_type="screen_capture", content=image, confidence=1.0,
        permissions_required=("screen_capture",), retention_policy=RETENTION_EPHEMERAL,
    )


def screen_ocr_source() -> PerceptionObservation:
    """Real screen capture immediately followed by real OCR -- one
    composite PERCEPTION_OCR observation whose `content` is the
    structured `OCRResult` (text + real word-level boxes/confidence),
    not the raw image (the raw pixels are already available via
    PERCEPTION_VISION if a caller separately needs them). Confidence
    on the observation itself is the mean of the real per-word OCR
    confidences (0.0 if no words were recognized), never hardcoded.
    """
    image = capture_screen()
    result = extract_text(image)
    confidence = (
        sum(w.confidence for w in result.words) / len(result.words) if result.words else 0.0
    )
    return PerceptionObservation(
        source=PERCEPTION_OCR, observation_type="screen_ocr", content=result, confidence=confidence,
        permissions_required=("screen_capture", "ocr"), retention_policy=RETENTION_EPHEMERAL,
    )
