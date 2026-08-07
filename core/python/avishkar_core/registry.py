"""ModuleRegistry -- registration and lifecycle for frameworks, agents,
and shelf-packages.

See CONTRACT.md SS4 for the full contract, and
schemas/module-manifest.schema.json for the manifest shape.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, List, Optional, Tuple

from .errors import (
    DependencyDirectionError,
    InvalidManifestError,
    ModuleAlreadyRegisteredError,
    ModuleNotRegisteredError,
)
from .event_bus import EventBus
from .logging import get_logger

_logger = get_logger("core.registry")

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")
_VALID_KINDS = {"framework", "agent", "shelf-package"}


@dataclasses.dataclass(frozen=True)
class ModuleManifest:
    """What a framework/agent/shelf-package declares to register itself.
    Validated against schemas/module-manifest.schema.json's rules on
    construction.
    """

    name: str
    version: str
    kind: str
    description: str = ""
    dependencies: Tuple[str, ...] = ("core",)

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.match(self.name):
            raise InvalidManifestError(f"Manifest name '{self.name}' must be kebab-case")
        if not _VERSION_PATTERN.match(self.version):
            raise InvalidManifestError(f"Manifest version '{self.version}' must be semantic (x.y.z)")
        if self.kind not in _VALID_KINDS:
            raise InvalidManifestError(
                f"Manifest kind '{self.kind}' must be one of {sorted(_VALID_KINDS)}"
            )


@dataclasses.dataclass
class RegisteredModule:
    manifest: ModuleManifest
    instance: Any = None


class ModuleRegistry:
    """Tracks every framework/agent/shelf-package that registers itself,
    and coordinates their startup/shutdown order. Registration is
    optional -- a module with no lifecycle hooks or discovery need has no
    obligation to register (see CONTRACT.md SS4).
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._modules: Dict[str, RegisteredModule] = {}
        self._order: List[str] = []
        self._event_bus = event_bus or EventBus()

    def register(self, manifest: ModuleManifest, instance: Any = None, replace: bool = False) -> None:
        if manifest.name in self._modules and not replace:
            raise ModuleAlreadyRegisteredError(
                f"Module '{manifest.name}' is already registered "
                f"(pass replace=True to intentionally replace it)"
            )
        # Enforces ARCHITECTURE.md SS5: Avishkar OS modules must never
        # depend on an application. No application registry exists yet
        # for a manifest to violate against, but the guard is wired in
        # now so a future application-facing registry can't silently
        # skip it -- see CONTRACT.md SS4.
        for dependency in manifest.dependencies:
            if dependency.startswith("app:"):
                raise DependencyDirectionError(
                    f"Module '{manifest.name}' declares dependency '{dependency}' -- "
                    f"Avishkar OS modules must never depend on an application "
                    f"(ARCHITECTURE.md SS5)"
                )
        if manifest.name not in self._modules:
            self._order.append(manifest.name)
        self._modules[manifest.name] = RegisteredModule(manifest=manifest, instance=instance)
        _logger.info(
            f"Module '{manifest.name}' registered",
            kind=manifest.kind,
            version=manifest.version,
        )
        self._event_bus.publish("core.module.registered", {"name": manifest.name}, source="core.registry")

    def get(self, name: str) -> RegisteredModule:
        try:
            return self._modules[name]
        except KeyError as exc:
            raise ModuleNotRegisteredError(f"No module named '{name}' is registered") from exc

    def list(self, kind: Optional[str] = None) -> List[RegisteredModule]:
        modules = [self._modules[name] for name in self._order]
        if kind is not None:
            modules = [m for m in modules if m.manifest.kind == kind]
        return modules

    def unregister(self, name: str) -> None:
        if name in self._modules:
            del self._modules[name]
            self._order.remove(name)

    def start_all(self) -> None:
        """Calls instance.on_start() (if defined) for every registered
        module, in registration order, then publishes
        'core.module.started'.
        """
        for name in self._order:
            instance = self._modules[name].instance
            on_start = getattr(instance, "on_start", None)
            if callable(on_start):
                on_start()
            self._event_bus.publish("core.module.started", {"name": name}, source="core.registry")

    def stop_all(self) -> None:
        """Calls instance.on_stop() (if defined) in REVERSE registration
        order, then publishes 'core.module.stopped'.
        """
        for name in reversed(self._order):
            instance = self._modules[name].instance
            on_stop = getattr(instance, "on_stop", None)
            if callable(on_stop):
                on_stop()
            self._event_bus.publish("core.module.stopped", {"name": name}, source="core.registry")
