"""Vision / OCR / Spatial Intelligence -- Mission Layla Directive D,
Part II. See CONTRACT.md SS33.

Camera/Screen -> Capture -> Vision Pipeline (OCR/Detection/Spatial
Analysis) -> structured PerceptionObservation -> Layla Context ->
Decision. Every function here produces DATA -- never calls a tool,
executor, or `ExecutiveRuntime.handle_event()` itself. Directive D
Part II, verbatim: "Do not allow raw perception outputs to directly
execute dangerous actions. Perception must produce structured evidence
that passes through Layla's decision/risk architecture." This module
wires real capture/analysis functions as `PerceptionCapture` callables
for `avishkar_layla.perception.PerceptionEngine.register_capture()` --
it does not create a second perception framework.

- ScreenCapture: REAL, LOCAL. `PIL.ImageGrab`-backed, genuinely
  captures this machine's real screen. Like voice's
  MicrophoneFrameSource, never invoked against the LIVE screen by the
  automated test suite (see screen_capture.py's module docstring for
  why) -- OCR/detection/spatial logic is instead tested for real
  against a synthetically-rendered test image.
- OCR: REAL if the `tesseract` binary is installed on this machine
  (`pytesseract` is a thin wrapper around it, not a standalone OCR
  engine) -- `is_tesseract_available()` reports which. Real word-level
  bounding boxes and per-word confidence from `pytesseract.image_to_data`,
  never fabricated.
- Spatial: REAL. Pure geometry over real bounding-box coordinates
  (relative position, distance, overlap, nearest-neighbor) -- no
  external dependency.
- Detection: REAL, template-based. `cv2.matchTemplate` -- finds a
  known reference image inside a larger one with a genuine similarity
  score. Not a trained object/scene classifier (see README.md Vision
  section for what's explicitly NOT built this pass).
"""

from __future__ import annotations

from .detection import DetectionMatch, detect_template, is_opencv_available
from .errors import OCRNotAvailableError, ScreenCaptureError
from .ocr import OCRResult, OCRWord, extract_text, is_tesseract_available
from .perception_adapters import screen_capture_source, screen_ocr_source
from .screen_capture import capture_screen
from .spatial import BoundingBox, distance, nearest, overlaps, relative_position

__all__ = [
    "BoundingBox",
    "DetectionMatch",
    "OCRNotAvailableError",
    "OCRResult",
    "OCRWord",
    "ScreenCaptureError",
    "capture_screen",
    "detect_template",
    "distance",
    "extract_text",
    "is_opencv_available",
    "is_tesseract_available",
    "nearest",
    "overlaps",
    "relative_position",
    "screen_capture_source",
    "screen_ocr_source",
]
