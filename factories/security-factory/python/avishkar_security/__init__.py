"""avishkar_security -- Python reference implementation of the
Security Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.
"""

from .agent_bridge import (
    make_input_validation_guardrail,
    make_rate_limit_guardrail,
    make_secret_scanning_guardrail,
)
from .checklist import SECURITY_CHECKLIST
from .errors import MissingAnswerError, SecurityFrameworkError, UnknownChecklistItemError
from .review import run_checklist
from .scanners import redact_secrets, scan_for_secrets, scan_repository_for_secrets
from .types import ChecklistItem, ChecklistResult, RepositoryFinding, ReviewReport, SecretMatch

__version__ = "0.1.0"

__all__ = [
    "SecretMatch",
    "RepositoryFinding",
    "scan_for_secrets",
    "redact_secrets",
    "scan_repository_for_secrets",
    "ChecklistItem",
    "ChecklistResult",
    "ReviewReport",
    "SECURITY_CHECKLIST",
    "run_checklist",
    "make_secret_scanning_guardrail",
    "make_rate_limit_guardrail",
    "make_input_validation_guardrail",
    "SecurityFrameworkError",
    "MissingAnswerError",
    "UnknownChecklistItemError",
    "__version__",
]
