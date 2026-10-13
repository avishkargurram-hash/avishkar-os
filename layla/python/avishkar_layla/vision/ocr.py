"""Optical Character Recognition. See CONTRACT.md SS33.

STATUS: REAL if the `tesseract` binary is installed on this machine.
`pytesseract` is a thin subprocess wrapper around the real Tesseract
OCR engine, not a standalone OCR implementation -- `is_tesseract_available()`
reports whether the binary is actually reachable, and `extract_text()`
raises `OCRNotAvailableError` (ADAPTER READY) rather than fabricating
a transcript if it isn't. Word-level bounding boxes and per-word
confidence come directly from Tesseract's own `image_to_data` output
-- real values, never synthesized.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import shutil
from typing import Tuple

from .errors import OCRNotAvailableError
from .spatial import BoundingBox

# Real, well-known Windows install locations for the UB-Mannheim
# Tesseract-OCR distribution, which does not always add itself to
# PATH depending on install options. Checked only as a fallback, after
# PATH itself -- never a fabricated location, an actual default the
# real installer uses.
_WINDOWS_FALLBACK_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _discover_tesseract_cmd():
    if shutil.which("tesseract"):
        return "tesseract"
    for candidate in _WINDOWS_FALLBACK_PATHS:
        if os.path.isfile(candidate):
            return candidate
    return None


@dataclasses.dataclass(frozen=True)
class OCRWord:
    text: str
    confidence: float  # 0.0-1.0, real value from the OCR engine
    box: BoundingBox


@dataclasses.dataclass(frozen=True)
class OCRResult:
    text: str
    words: Tuple[OCRWord, ...]


@functools.lru_cache(maxsize=1)
def is_tesseract_available() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    cmd = _discover_tesseract_cmd()
    if cmd is None:
        return False
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text(image) -> OCRResult:
    """`image` is any object pytesseract accepts (a real PIL.Image, a
    numpy array, or a file path) -- deliberately not typed narrowly so
    both a live screen_capture() result and a synthetic test image
    work identically.
    """
    if not is_tesseract_available():
        raise OCRNotAvailableError(
            "the 'tesseract' binary is not installed/discoverable on this machine -- this is the "
            "documented ADAPTER READY boundary (CONTRACT.md SS33): install Tesseract OCR "
            "(https://github.com/UB-Mannheim/tesseract/wiki on Windows, `apt install tesseract-ocr` on "
            "Debian/Ubuntu, `brew install tesseract` on macOS) before using extract_text() in production."
        )

    import pytesseract
    from pytesseract import Output

    data = pytesseract.image_to_data(image, output_type=Output.DICT)

    words = []
    n = len(data["text"])
    for i in range(n):
        raw_text = data["text"][i].strip()
        if not raw_text:
            continue
        conf_raw = data["conf"][i]
        try:
            confidence = max(0.0, float(conf_raw)) / 100.0
        except (TypeError, ValueError):
            confidence = 0.0
        box = BoundingBox(
            x0=data["left"][i], y0=data["top"][i],
            x1=data["left"][i] + data["width"][i], y1=data["top"][i] + data["height"][i],
        )
        words.append(OCRWord(text=raw_text, confidence=confidence, box=box))

    full_text = " ".join(w.text for w in words)
    return OCRResult(text=full_text, words=tuple(words))
