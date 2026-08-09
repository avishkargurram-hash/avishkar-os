"""Workflow Framework bridge. See CONTRACT.md SS5.

A pure consumer of avishkar_workflow's already-public WorkflowResult
type -- no changes to workflow-factory's locked source.
"""

from __future__ import annotations

from avishkar_workflow import WorkflowResult

from .runner import run_suite
from .types import EvalReport, EvalSuite, Scorer


def evaluate_workflow_result(
    result: WorkflowResult,
    suite: EvalSuite,
    scorer: Scorer,
    *,
    output_key: str = "output",
) -> EvalReport:
    actual = str(result.state[output_key])
    return run_suite(suite, lambda case: actual, scorer)
