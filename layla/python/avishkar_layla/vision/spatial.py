"""Spatial Intelligence: real geometry over real bounding-box
coordinates. See CONTRACT.md SS33.

STATUS: REAL. No external dependency, no model, no fabricated
relationship -- every function here is a direct, deterministic
computation over the (x0, y0, x1, y1) boxes OCR/detection produce.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Optional, Sequence


@dataclasses.dataclass(frozen=True)
class BoundingBox:
    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"invalid bounding box: {self!r} (x1 must be >= x0, y1 must be >= y0)")

    @property
    def center(self) -> "tuple[float, float]":
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height


def distance(a: BoundingBox, b: BoundingBox) -> float:
    ax, ay = a.center
    bx, by = b.center
    return math.hypot(ax - bx, ay - by)


def overlaps(a: BoundingBox, b: BoundingBox) -> bool:
    return a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1


def _overlap_area(a: BoundingBox, b: BoundingBox) -> int:
    if not overlaps(a, b):
        return 0
    ox0, oy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ox1, oy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    return (ox1 - ox0) * (oy1 - oy0)


def iou(a: BoundingBox, b: BoundingBox) -> float:
    """Real intersection-over-union -- the standard detection-overlap
    metric, useful for deduplicating near-identical matches.
    """
    inter = _overlap_area(a, b)
    if inter == 0:
        return 0.0
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def relative_position(a: BoundingBox, b: BoundingBox) -> str:
    """Describes where `a` sits relative to `b`: real center-to-center
    geometry, not a guess. Overlap is checked first since "left of"/
    "above" are meaningless once two boxes overlap significantly.
    """
    if overlaps(a, b) and iou(a, b) > 0.1:
        return "overlapping"
    ax, ay = a.center
    bx, by = b.center
    dx, dy = ax - bx, ay - by
    if abs(dx) >= abs(dy):
        return "right_of" if dx > 0 else "left_of"
    return "below" if dy > 0 else "above"


def nearest(target: BoundingBox, candidates: Sequence[BoundingBox]) -> Optional[BoundingBox]:
    """Real nearest-neighbor by center-to-center Euclidean distance.
    Returns None for an empty candidate list rather than raising --
    "no candidates" is a normal outcome, not an error.
    """
    if not candidates:
        return None
    return min(candidates, key=lambda c: distance(target, c))
