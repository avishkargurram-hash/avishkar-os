"""Agent Framework guardrail bridges. See CONTRACT.md SS3.

Real, reusable avishkar_agent.Guardrails -- pure consumers of
agent-factory's already-public type, no changes to its locked source
(ADR-0011's dependency-direction discipline, continued).
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from avishkar_agent import Guardrail, Task

from .scanners import scan_for_secrets


def make_secret_scanning_guardrail(name: str = "no-secrets-in-input") -> Guardrail:
    def check(task: Task) -> Optional[str]:
        matches = scan_for_secrets(task.input)
        if matches:
            found = ", ".join(sorted({m.pattern_name for m in matches}))
            return f"input appears to contain a secret ({found})"
        return None

    return Guardrail(name=name, check=check)


def make_rate_limit_guardrail(
    name: str,
    max_calls: int,
    window_seconds: float,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Guardrail:
    call_times: List[float] = []

    def check(task: Task) -> Optional[str]:
        now = clock()
        cutoff = now - window_seconds
        while call_times and call_times[0] < cutoff:
            call_times.pop(0)
        if len(call_times) >= max_calls:
            return f"rate limit exceeded: {max_calls} calls per {window_seconds}s"
        call_times.append(now)
        return None

    return Guardrail(name=name, check=check)


def make_input_validation_guardrail(name: str, validator: Callable[[str], Optional[str]]) -> Guardrail:
    def check(task: Task) -> Optional[str]:
        return validator(task.input)

    return Guardrail(name=name, check=check)
