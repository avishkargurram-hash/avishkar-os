"""avishkar_prompt -- Python reference implementation of the Prompt
Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.
"""

from .errors import (
    DuplicateVersionError,
    MissingVariableError,
    PromptFrameworkError,
    UnknownVariableError,
    UnknownVersionError,
)
from .registry import PromptRegistry
from .render import render
from .scoring import (
    Scorer,
    compare_versions,
    evaluate_version,
    exact_match_scorer,
    keyword_presence_scorer,
)
from .types import EvalCase, EvalReport, PromptVariable, PromptVersion, RegressionResult

__version__ = "0.1.0"

__all__ = [
    "PromptVersion",
    "PromptVariable",
    "PromptRegistry",
    "render",
    "EvalCase",
    "EvalReport",
    "RegressionResult",
    "Scorer",
    "exact_match_scorer",
    "keyword_presence_scorer",
    "evaluate_version",
    "compare_versions",
    "PromptFrameworkError",
    "UnknownVariableError",
    "MissingVariableError",
    "DuplicateVersionError",
    "UnknownVersionError",
    "__version__",
]
