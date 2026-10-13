"""Core data types for the Starter Kit Framework. See CONTRACT.md SS0-1."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Tuple

from avishkar_agent import AgentBlueprint
from avishkar_template import Template


@dataclasses.dataclass(frozen=True)
class StarterKit:
    """A named, versioned, clone-and-go product starting point.
    See CONTRACT.md SS1.
    """

    name: str
    version: str
    description: str
    blueprint: AgentBlueprint
    project_template: Template
    components: Tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class StarterKitResult:
    """Returned by materialize(). See CONTRACT.md SS3."""

    written: Tuple[Path, ...]
