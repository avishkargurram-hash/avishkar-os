"""Instantiation. See CONTRACT.md SS4."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Tuple

from avishkar_prompt import render

from .errors import TemplateInstantiationError
from .types import Template


def instantiate(
    template: Template,
    target_dir: Path,
    values: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> Tuple[Path, ...]:
    target_dir = Path(target_dir)
    written = []

    # Validate before writing anything -- a partially-instantiated
    # template on disk (some files written, then a collision error
    # halfway through) would be worse than refusing up front.
    if not overwrite:
        collisions = [
            target_dir / file.relative_path
            for file in template.files
            if (target_dir / file.relative_path).exists()
        ]
        if collisions:
            raise TemplateInstantiationError(
                f"refusing to overwrite existing file(s) without overwrite=True: "
                f"{[str(p) for p in collisions]}"
            )

    for file in template.files:
        target_path = target_dir / file.relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(render(file.spec, values), encoding="utf-8")
        written.append(target_path)

    return tuple(written)
