"""WorkflowSpec + WorkflowEngine -- the step engine itself.
See CONTRACT.md SS3-4.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Mapping, Optional

from avishkar_core import get_logger

from .errors import (
    DuplicateStepError,
    MaxStepsExceededError,
    StepExecutionError,
    UnknownStepError,
)
from .types import State, Step, WorkflowResult


class WorkflowSpec:
    """An ordered/branching collection of Steps. See CONTRACT.md SS3.

    Validated eagerly at construction: duplicate step ids and unknown
    static `next` targets fail fast here rather than mid-run, since both
    are structural mistakes a caller can (and should) catch before ever
    executing anything.
    """

    def __init__(self, workflow_id: str, steps: Iterable[Step], start: str) -> None:
        steps = tuple(steps)
        by_id: dict[str, Step] = {}
        for step in steps:
            if step.id in by_id:
                raise DuplicateStepError(f"duplicate step id: {step.id!r}")
            by_id[step.id] = step

        if start not in by_id:
            raise UnknownStepError(f"start step {start!r} is not among the workflow's steps")

        for step in steps:
            if step.next is not None and step.next not in by_id:
                raise UnknownStepError(
                    f"step {step.id!r}.next names unknown step {step.next!r}"
                )

        self.id = workflow_id
        self.start = start
        self._steps = by_id

    @property
    def steps(self) -> Mapping[str, Step]:
        return self._steps


class WorkflowEngine:
    """Executes a WorkflowSpec. See CONTRACT.md SS4."""

    def __init__(
        self,
        *,
        logger: Optional[object] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._logger = logger or get_logger("workflow.engine")
        self._sleep_fn = sleep_fn

    def run(self, spec: WorkflowSpec, initial_state: State, *, max_steps: int = 1000) -> WorkflowResult:
        state: dict = dict(initial_state)
        history: list[str] = []
        current_id: Optional[str] = spec.start

        while current_id is not None:
            if len(history) >= max_steps:
                raise MaxStepsExceededError(
                    f"workflow {spec.id!r} exceeded max_steps={max_steps} "
                    f"(last step: {current_id!r}); check for an unintended branch cycle"
                )

            step = spec.steps.get(current_id)
            if step is None:
                raise UnknownStepError(
                    f"branch from a prior step named unknown step {current_id!r}"
                )

            history.append(step.id)
            update = self._run_step_with_retry(step, state)
            state = {**state, **update}

            if step.branch is not None:
                current_id = step.branch(state)
            else:
                current_id = step.next

        self._logger.info("workflow completed", workflow_id=spec.id, steps=len(history))
        return WorkflowResult(state=state, history=tuple(history), status="completed")

    def _run_step_with_retry(self, step: Step, state: State) -> Mapping:
        policy = step.retry_policy
        last_error: Optional[Exception] = None
        for attempt in range(1, max(1, policy.max_attempts) + 1):
            try:
                return step.handler(state)
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, re-raised below
                last_error = exc
                self._logger.warning(
                    "step failed", step_id=step.id, attempt=attempt, error=str(exc)
                )
                if attempt < policy.max_attempts:
                    self._sleep_fn(policy.backoff_seconds)

        raise StepExecutionError(
            f"step {step.id!r} failed after {policy.max_attempts} attempt(s)"
        ) from last_error
