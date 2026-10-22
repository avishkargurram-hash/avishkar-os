"""Tool Registry (spec section 12, 35).

Tools are never hardcoded into the Scientist Core: handlers look them up
here by name and call them through `Registry.call`, which

* enforces permissions -- a task type may only use tools whose permissions
  are all granted to it (TASK_GRANTS); anything else raises ToolDenied;
* enforces the tool's timeout (passed to the tool) and the per-mission
  tool-call budget;
* writes every call (ok / error / denied) to the tool_calls ledger.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional


class ToolDenied(Exception):
    """The calling task is not permitted to use this tool."""


class ToolError(Exception):
    """The tool ran and failed (network, provider, sandbox...)."""


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    category: str                  # spec section 12 categories, e.g. ACADEMIC_SEARCH
    description: str
    version: str
    permissions: tuple             # e.g. ("net.academic",), ("sandbox.exec",)
    input_schema: dict
    output_schema: dict
    cost: float                    # USD per call (0 for free APIs / local)
    timeout_s: float
    security_policy: str           # human-readable policy statement
    fn: Callable[..., Any] = dataclasses.field(repr=False, compare=False, default=None)


# task type -> permissions it holds. Least privilege: only the experiment
# and replication workers may touch the sandbox; only literature workers
# may reach the network.
TASK_GRANTS: Dict[str, frozenset] = {
    "lit.search": frozenset({"net.academic"}),
    "source.analyze": frozenset({"net.academic"}),
    "experiment.run": frozenset({"sandbox.exec"}),
    "replication.run": frozenset({"sandbox.exec"}),
    "analysis.stats": frozenset({"compute.local"}),
}


class Registry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self, category: Optional[str] = None) -> list:
        return sorted(n for n, s in self._tools.items() if category is None or s.category == category)

    def describe(self) -> list:
        return [{k: v for k, v in dataclasses.asdict(s).items() if k != "fn"} for s in self._tools.values()]

    def call(self, name: str, *, task_type: str, db=None, mission_id: Optional[str] = None,
             task_id: Optional[int] = None, max_tool_calls: Optional[int] = None, **kwargs) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolDenied(f"unknown tool {name}")
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()[:16]
        granted = TASK_GRANTS.get(task_type, frozenset())
        missing = set(spec.permissions) - granted
        if missing:
            self._ledger(db, mission_id, task_id, spec, "denied", digest, 0, f"missing permissions {sorted(missing)}")
            raise ToolDenied(f"task {task_type} may not use {name} (needs {sorted(missing)})")
        if db is not None and mission_id and max_tool_calls is not None:
            used = db.one("SELECT COALESCE(tool_calls,0) AS n FROM budgets WHERE mission_id=%s", (mission_id,))
            if used and used["n"] >= max_tool_calls:
                self._ledger(db, mission_id, task_id, spec, "denied", digest, 0, "mission tool budget exhausted")
                raise ToolDenied("mission tool-call budget exhausted")
        t0 = time.monotonic()
        try:
            out = spec.fn(timeout_s=spec.timeout_s, **kwargs)
        except ToolDenied:
            raise
        except Exception as exc:  # noqa: BLE001 -- ledger every failure, re-raise typed
            self._ledger(db, mission_id, task_id, spec, "error", digest, int((time.monotonic() - t0) * 1000),
                         f"{type(exc).__name__}: {exc}"[:800])
            raise ToolError(f"{name}: {exc}") from exc
        self._ledger(db, mission_id, task_id, spec, "ok", digest, int((time.monotonic() - t0) * 1000), None)
        return out

    @staticmethod
    def _ledger(db, mission_id, task_id, spec, status, digest, ms, err) -> None:
        if db is None:
            return
        with db.tx() as c:
            c.execute("INSERT INTO tool_calls(mission_id, task_id, tool, version, status, input_digest, latency_ms, error) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (mission_id, task_id, spec.name, spec.version, status, digest, ms, err))
            if mission_id and status == "ok":
                c.execute("INSERT INTO budgets(mission_id, tool_calls) VALUES (%s,1) ON CONFLICT (mission_id) "
                          "DO UPDATE SET tool_calls=budgets.tool_calls+1, updated_at=now()", (mission_id,))
