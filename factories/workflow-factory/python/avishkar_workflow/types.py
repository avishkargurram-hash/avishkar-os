"""Core data types for the Workflow Framework. See CONTRACT.md SS1-3, SS5.

`RetryPolicy` is reused verbatim from `avishkar_integration` (Phase 4)
rather than redefined -- the same DRY discipline ADR-0011 established
for `Tool` and ADR-0011/Phase-5/6 continued for `MemoryPolicy`. This is
the third framework to reuse it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Mapping, Optional, Tuple

from avishkar_integration import RetryPolicy

__all__ = [
    "RetryPolicy",
    "State",
    "PartialState",
    "NodeFn",
    "BranchFn",
    "Step",
    "WorkflowResult",
]

State = Mapping[str, Any]
PartialState = Mapping[str, Any]
NodeFn = Callable[[State], PartialState]
BranchFn = Callable[[State], Optional[str]]


@dataclasses.dataclass(frozen=True)
class Step:
    """One node in a WorkflowSpec. See CONTRACT.md SS2."""

    id: str
    handler: NodeFn
    next: Optional[str] = None
    branch: Optional[BranchFn] = None
    retry_policy: RetryPolicy = dataclasses.field(default_factory=RetryPolicy)


@dataclasses.dataclass(frozen=True)
class WorkflowResult:
    """Returned by WorkflowEngine.run(). See CONTRACT.md SS5."""

    state: Mapping[str, Any]
    history: Tuple[str, ...]
    status: str = "completed"
