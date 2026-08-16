"""Errors for the vision subsystem. See CONTRACT.md SS33."""

from __future__ import annotations

from ..errors import LaylaError


class ScreenCaptureError(LaylaError):
    """A real screen-capture attempt failed (no display, permission
    denied, capture library missing)."""


class OCRNotAvailableError(LaylaError):
    """extract_text() was called but the `tesseract` binary isn't
    installed/discoverable -- the documented ADAPTER READY boundary.
    pytesseract is a wrapper, not an OCR engine; it needs the real
    binary present on PATH (or `pytesseract.pytesseract.tesseract_cmd`
    pointed at it).
    """
