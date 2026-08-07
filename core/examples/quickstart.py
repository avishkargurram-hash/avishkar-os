"""Core Engine Framework -- quickstart.

Demonstrates all four capabilities together: a toy framework loads its
config, gets a logger, registers itself with lifecycle hooks, and reacts
to another module's event. This is the "at least one runnable example"
STANDARDS.md SS2.2 requires -- run it directly:

    python core/examples/quickstart.py

No installation needed: this script adds core/python to sys.path itself
so it runs straight out of a fresh clone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from avishkar_core import (  # noqa: E402
    EventBus,
    ModuleManifest,
    ModuleRegistry,
    get_logger,
    load_config,
)


class GreeterFramework:
    """A toy framework standing in for a real one (e.g. agent-factory).
    Shows the shape every framework's own on_start/on_stop follows.
    """

    def __init__(self, config, logger, event_bus: EventBus) -> None:
        self._config = config
        self._logger = logger
        self._event_bus = event_bus

    def on_start(self) -> None:
        self._logger.info("GreeterFramework starting", greeting=self._config.get("greeting"))
        self._event_bus.subscribe("core.module.registered", self._on_module_registered)

    def on_stop(self) -> None:
        self._logger.info("GreeterFramework stopping")

    def greet(self, name: str) -> str:
        message = f"{self._config.require('greeting')}, {name}!"
        self._logger.info("Greeted someone", target=name)
        return message

    def _on_module_registered(self, event) -> None:
        self._logger.debug("Saw another module register", other_module=event.payload["name"])


def main() -> None:
    # 1. Config -- layered: code defaults, overridden here as if by an
    #    env var (AVISHKAR_GREETING=Howdy) for demonstration.
    config = load_config(
        defaults={"greeting": "Hello"},
        overrides={"greeting": "Howdy"},
    )

    # 2. Logger -- structured, one call per module name.
    logger = get_logger("examples.quickstart")

    # 3. EventBus -- shared by everything registered below.
    event_bus = EventBus()

    # 4. ModuleRegistry -- registers the toy framework with a real
    #    manifest and runs its lifecycle.
    registry = ModuleRegistry(event_bus=event_bus)
    greeter = GreeterFramework(config, get_logger("greeter-framework"), event_bus)
    registry.register(
        ModuleManifest(name="greeter-framework", version="0.1.0", kind="framework"),
        instance=greeter,
    )

    registry.start_all()
    print(greeter.greet("Avishkar Labs"))

    # A second module registering fires the event GreeterFramework
    # subscribed to in on_start().
    registry.register(ModuleManifest(name="second-framework", version="0.1.0", kind="framework"))

    registry.stop_all()

    logger.info("Quickstart complete", modules_registered=len(registry.list()))


if __name__ == "__main__":
    main()
