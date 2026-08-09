"""avishkar_starter_kit -- Python reference implementation of the
Starter Kit Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.
"""

from .builtin import AGENT_WITH_MEMORY_AND_KNOWLEDGE
from .errors import DuplicateVersionError, StarterKitFrameworkError, UnknownVersionError
from .materialize import materialize
from .registry import StarterKitRegistry
from .types import StarterKit, StarterKitResult

__version__ = "0.1.0"

__all__ = [
    "StarterKit",
    "StarterKitResult",
    "StarterKitRegistry",
    "materialize",
    "AGENT_WITH_MEMORY_AND_KNOWLEDGE",
    "StarterKitFrameworkError",
    "DuplicateVersionError",
    "UnknownVersionError",
    "__version__",
]
