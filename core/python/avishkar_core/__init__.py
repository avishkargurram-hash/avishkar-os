"""avishkar_core -- Python reference implementation of the Core Engine Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation
(Vision, Architecture, Extension Model, Best Practices, Anti-Patterns).
"""

from .config import Config, load_config
from .errors import (
    AvishkarCoreError,
    ConfigError,
    DependencyDirectionError,
    InvalidManifestError,
    ModuleAlreadyRegisteredError,
    ModuleNotRegisteredError,
)
from .event_bus import Event, EventBus, Subscription
from .logging import Logger, get_logger
from .registry import ModuleManifest, ModuleRegistry, RegisteredModule

__version__ = "0.1.0"

__all__ = [
    "Config",
    "load_config",
    "AvishkarCoreError",
    "ConfigError",
    "DependencyDirectionError",
    "InvalidManifestError",
    "ModuleAlreadyRegisteredError",
    "ModuleNotRegisteredError",
    "Event",
    "EventBus",
    "Subscription",
    "Logger",
    "get_logger",
    "ModuleManifest",
    "ModuleRegistry",
    "RegisteredModule",
    "__version__",
]
