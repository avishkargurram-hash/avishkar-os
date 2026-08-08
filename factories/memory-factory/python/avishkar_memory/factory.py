"""build_memory_policy -- resolves an avishkar_agent.MemoryPolicyConfig
(already declared by any Chief Domain Agent's blueprint.json) against a
real backend. Closes the seam agent-factory/README.md's Future Roadmap
named: "Persistent memory backends once memory-factory ships." See
CONTRACT.md SS2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from avishkar_agent import InMemoryMemoryPolicy, MemoryPolicy, MemoryPolicyConfig

from .backends import FileMemoryPolicy, SQLiteMemoryPolicy
from .errors import UnknownBackendError


def build_memory_policy(
    config: MemoryPolicyConfig,
    *,
    root_dir: Optional[Union[str, Path]] = None,
    db_path: Optional[str] = None,
) -> MemoryPolicy:
    if config.backend == "in_memory":
        return InMemoryMemoryPolicy()
    if config.backend == "file":
        return FileMemoryPolicy(root_dir or Path("./.avishkar_memory"))
    if config.backend == "sqlite":
        return SQLiteMemoryPolicy(db_path or ":memory:")
    raise UnknownBackendError(
        f"MemoryPolicyConfig.backend='{config.backend}' has no matching backend "
        f"(expected 'in_memory', 'file', or 'sqlite')"
    )
