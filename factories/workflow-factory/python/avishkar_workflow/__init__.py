"""avishkar_workflow -- Python reference implementation of the Workflow
Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.

Per DECISIONS.md ADR-0013: an in-process step engine whose steps are
plain Callable[[State], PartialState] -- LangGraph's own node shape --
with zero `langgraph`/`n8n` dependency. `langgraph-factory` and
`n8n-factory` remain deferred (ADR-0009).
"""

from .bridges import (
    make_agent_step,
    make_knowledge_search_step,
    make_memory_read_step,
    make_memory_write_step,
)
from .errors import (
    DuplicateStepError,
    MaxStepsExceededError,
    StepExecutionError,
    UnknownStepError,
    WorkflowFrameworkError,
)
from .types import PartialState, RetryPolicy, State, Step, WorkflowResult
from .workflow import WorkflowEngine, WorkflowSpec

__version__ = "0.1.0"

__all__ = [
    "WorkflowSpec",
    "WorkflowEngine",
    "WorkflowResult",
    "Step",
    "State",
    "PartialState",
    "RetryPolicy",
    "make_agent_step",
    "make_knowledge_search_step",
    "make_memory_read_step",
    "make_memory_write_step",
    "WorkflowFrameworkError",
    "DuplicateStepError",
    "UnknownStepError",
    "StepExecutionError",
    "MaxStepsExceededError",
    "__version__",
]
