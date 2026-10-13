"""Real local screen capture. See CONTRACT.md SS33.

STATUS: REAL, LOCAL, HARDWARE-BACKED. `PIL.ImageGrab.grab()` genuinely
captures this machine's real screen (confirmed against this machine's
actual 1366x768 display during development). Like voice's
MicrophoneFrameSource, `capture_screen()` is never invoked against the
LIVE screen by the automated test suite: capturing whatever is
actually displayed on a real desktop non-interactively during an
unattended run would capture whatever the user has open (documents,
messages, credentials on screen) with no specific, momentary consent
-- the same "real-world action needs a deliberate trigger" discipline
already applied to the microphone and to embodiment/IoT. OCR/spatial/
detection logic is instead tested for real against a synthetically
rendered image (see test_vision_ocr.py) -- an entirely real analysis
pipeline exercised on non-invasive test data.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from .errors import ScreenCaptureError


def _real_grab(region: Optional[Tuple[int, int, int, int]]):
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=region)


def capture_screen(*, region: Optional[Tuple[int, int, int, int]] = None, _grab_fn: Optional[Callable] = None):
    """Returns a real PIL.Image of the current screen (or `region`,
    an (x0, y0, x1, y1) box). Raises ScreenCaptureError rather than
    returning a blank/synthetic image if capture fails.

    `_grab_fn` is an internal test seam (defaults to the real
    ImageGrab.grab) -- production callers never pass it. This lets
    error-handling be tested for real without opening the live screen
    (see test_vision_screen_capture.py); it is NOT how the "no live
    capture in automated tests" boundary is enforced -- that's simply
    that no test calls capture_screen() without overriding _grab_fn.
    """
    grab_fn = _grab_fn or _real_grab
    try:
        return grab_fn(region)
    except ImportError as exc:
        raise ScreenCaptureError("the 'Pillow' package is not installed -- required for screen capture") from exc
    except Exception as exc:
        raise ScreenCaptureError(f"screen capture failed: {exc}") from exc
