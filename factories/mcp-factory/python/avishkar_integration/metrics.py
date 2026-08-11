"""MetricsCollector -- call counts, error rates, latency, and cost per
tool. See CONTRACT.md SS5 (ToolRuntime).

Most MCP/REST tool calls have no per-call USD cost the way an LLM
completion does -- `cost` defaults to 0.0 and only accumulates when a
ToolContract's `protocol_config` declares a fixed `cost_per_call` (an
honest default, not a fabricated dollar figure).

Concurrency (Priority 17.4 platform-wide hardening pass, ADR-0024):
record() is a read-modify-write on several dicts (`self._counts[key]
= self._counts.get(key, 0) + 1`, etc) -- individually atomic dict ops
under the GIL, but the *combination* is not: two threads calling
ToolRuntime.execute() concurrently for the same tool could both read
the same starting count and both write back the same incremented
value, silently losing one increment. A lock around record() closes
this. Read methods are left unlocked -- they return a point-in-time
snapshot either way, and locking them adds no correctness that matters
for a metrics/observability surface. A narrow, additive exception to
mcp-factory's Phase 4 "locked" status -- justified because the Phase
17 directive explicitly names ToolRuntime as an audit/harden target;
every existing test still passes unmodified.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional


class MetricsCollector:
    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}
        self._latencies: Dict[str, List[float]] = {}
        self._cost: Dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, key: str, *, status: str, latency_ms: float, cost: float = 0.0) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            if status != "success":
                self._errors[key] = self._errors.get(key, 0) + 1
            self._latencies.setdefault(key, []).append(latency_ms)
            self._cost[key] = self._cost.get(key, 0.0) + cost

    def call_count(self, key: str) -> int:
        return self._counts.get(key, 0)

    def error_count(self, key: str) -> int:
        return self._errors.get(key, 0)

    def error_rate(self, key: str) -> float:
        total = self.call_count(key)
        return (self.error_count(key) / total) if total else 0.0

    def average_latency_ms(self, key: str) -> float:
        samples = self._latencies.get(key, [])
        return (sum(samples) / len(samples)) if samples else 0.0

    def total_cost(self, key: Optional[str] = None) -> float:
        if key is None:
            return sum(self._cost.values())
        return self._cost.get(key, 0.0)
