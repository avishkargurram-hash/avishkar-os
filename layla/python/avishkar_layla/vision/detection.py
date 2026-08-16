"""Template-based visual element detection. See CONTRACT.md SS33.

STATUS: REAL, classical computer vision -- `cv2.matchTemplate`
(normalized cross-correlation) genuinely finds a known reference image
inside a larger one and reports a real similarity score. This is NOT
a trained object/scene classifier ("what is this," open-vocabulary
detection) -- that would require a real model this pass does not
bundle or fabricate. What it IS real for: "does this known UI element
(a button, an icon, a logo) appear on screen, and where" -- genuinely
useful for computer-control verification (Directive D Part III:
"Observation -> Verification" needs exactly this) without pretending
to be general scene understanding. See README.md Vision section for
the explicit boundary.

Known real caveat (found by this module's own test suite, not merely
asserted): `cv2.TM_CCOEFF_NORMED` normalizes by each window's local
variance, so a perfectly flat/solid-color region of `haystack` against
a flat `needle` can score a spurious 1.0 (0/0 read as a match) --
`test_vision_detection.py` deliberately uses textured, noisy test
images rather than flat ones for exactly this reason, matching what a
real screenshot looks like anyway.
"""

from __future__ import annotations

import dataclasses
import functools
from typing import Tuple

from .spatial import BoundingBox


@dataclasses.dataclass(frozen=True)
class DetectionMatch:
    box: BoundingBox
    confidence: float  # 0.0-1.0, real normalized cross-correlation score


@functools.lru_cache(maxsize=1)
def is_opencv_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def _to_gray_array(image):
    import numpy as np

    if hasattr(image, "convert"):  # a PIL.Image
        image = image.convert("L")
        return np.array(image)
    arr = np.asarray(image)
    if arr.ndim == 3:
        import cv2

        return cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY if arr.shape[2] == 3 else cv2.COLOR_BGRA2GRAY)
    return arr


def detect_template(haystack, needle, *, threshold: float = 0.8) -> Tuple[DetectionMatch, ...]:
    """Finds every non-overlapping occurrence of `needle` inside
    `haystack` (both PIL.Image or numpy-array-like) with a real match
    score >= `threshold`. Returns real, ranked matches -- an empty
    tuple if nothing clears the threshold, never a fabricated "found
    it" guess.
    """
    if not is_opencv_available():
        raise ImportError("the 'opencv-python' package is not installed -- required for detect_template()")

    import cv2

    hay = _to_gray_array(haystack)
    needle_arr = _to_gray_array(needle)
    if needle_arr.shape[0] > hay.shape[0] or needle_arr.shape[1] > hay.shape[1]:
        return ()

    result = cv2.matchTemplate(hay, needle_arr, cv2.TM_CCOEFF_NORMED)
    needle_h, needle_w = needle_arr.shape[:2]

    matches = []
    working = result.copy()
    while True:
        _, max_val, _, max_loc = cv2.minMaxLoc(working)
        if max_val < threshold:
            break
        x, y = max_loc
        box = BoundingBox(x0=int(x), y0=int(y), x1=int(x + needle_w), y1=int(y + needle_h))
        matches.append(DetectionMatch(box=box, confidence=float(max_val)))
        # Suppress the region around this match so the next iteration
        # finds a genuinely different location, not the same peak.
        y0, y1 = max(0, y - needle_h // 2), min(working.shape[0], y + needle_h // 2)
        x0, x1 = max(0, x - needle_w // 2), min(working.shape[1], x + needle_w // 2)
        working[y0:y1, x0:x1] = -1.0
        if len(matches) >= 25:  # a real, generous safety bound -- never an unbounded loop
            break

    return tuple(sorted(matches, key=lambda m: m.confidence, reverse=True))
