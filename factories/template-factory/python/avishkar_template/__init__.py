"""avishkar_template -- Python reference implementation of the Template
Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.
"""

from .builtin import MODULE_README_TEMPLATE
from .errors import (
    DuplicateFileError,
    DuplicateVersionError,
    TemplateFrameworkError,
    TemplateInstantiationError,
    UnknownVersionError,
)
from .instantiate import instantiate
from .registry import TemplateRegistry
from .types import Template, TemplateFile

__version__ = "0.1.0"

__all__ = [
    "Template",
    "TemplateFile",
    "TemplateRegistry",
    "instantiate",
    "MODULE_README_TEMPLATE",
    "TemplateFrameworkError",
    "DuplicateFileError",
    "DuplicateVersionError",
    "UnknownVersionError",
    "TemplateInstantiationError",
    "__version__",
]
