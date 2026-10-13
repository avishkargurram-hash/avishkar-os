"""Materialization. See CONTRACT.md SS3."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping

from avishkar_template import TemplateInstantiationError, instantiate

from .types import StarterKit, StarterKitResult


def materialize(
    kit: StarterKit,
    target_dir: Path,
    values: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> StarterKitResult:
    target_dir = Path(target_dir)
    blueprint_path = target_dir / "agent" / "blueprint.json"

    # Same all-or-nothing discipline instantiate() itself follows (Phase
    # 9): check every collision -- including the blueprint manifest this
    # framework writes on top of the template -- before writing anything.
    if not overwrite and blueprint_path.exists():
        raise TemplateInstantiationError(
            f"refusing to overwrite existing file without overwrite=True: {blueprint_path}"
        )

    written = list(instantiate(kit.project_template, target_dir, values, overwrite=overwrite))

    blueprint_path.parent.mkdir(parents=True, exist_ok=True)
    blueprint_path.write_text(
        json.dumps(dataclasses.asdict(kit.blueprint), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(blueprint_path)

    return StarterKitResult(written=tuple(written))
