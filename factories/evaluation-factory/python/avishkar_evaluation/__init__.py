"""avishkar_evaluation -- Python reference implementation of the
Evaluation Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.

Per CONTRACT.md SS0: EvalCase/EvalReport/RegressionResult/Scorer are
reused verbatim from avishkar_prompt (Phase 8, ADR-0014) -- one
canonical scoring vocabulary shared by prompts, agents, and workflows.
"""

from avishkar_prompt import compare_versions, exact_match_scorer, keyword_presence_scorer

from .agent_bridge import make_quality_gate
from .errors import EmptyCaseSetError, EvaluationFrameworkError
from .runner import passes_threshold, run_suite
from .scorers import length_bounds_scorer, weighted_keyword_scorer
from .types import EvalCase, EvalReport, EvalSuite, RegressionResult, Scorer
from .workflow_bridge import evaluate_workflow_result

__version__ = "0.1.0"

__all__ = [
    "EvalCase",
    "EvalReport",
    "EvalSuite",
    "RegressionResult",
    "Scorer",
    "run_suite",
    "passes_threshold",
    "compare_versions",
    "exact_match_scorer",
    "keyword_presence_scorer",
    "length_bounds_scorer",
    "weighted_keyword_scorer",
    "make_quality_gate",
    "evaluate_workflow_result",
    "EvaluationFrameworkError",
    "EmptyCaseSetError",
    "__version__",
]
