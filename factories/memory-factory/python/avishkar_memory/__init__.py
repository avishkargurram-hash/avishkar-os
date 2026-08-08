"""avishkar_memory -- Python reference implementation of the Memory
Framework: real, persistent avishkar_agent.MemoryPolicy backends.

See ../CONTRACT.md and ../README.md for full documentation.
"""

from .backends import FileMemoryPolicy, SQLiteMemoryPolicy
from .errors import InvalidMemoryKindError, MemoryFrameworkError, UnknownBackendError
from .factory import build_memory_policy

__version__ = "0.1.0"

__all__ = [
    "FileMemoryPolicy",
    "SQLiteMemoryPolicy",
    "build_memory_policy",
    "MemoryFrameworkError",
    "UnknownBackendError",
    "InvalidMemoryKindError",
    "__version__",
]
