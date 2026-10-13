# Core Engine Framework

## Vision
Every other framework in Avishkar OS — all 13 factories, the AI Router,
every Chief Domain Agent — depends on being able to read config, log
consistently, react to what other modules are doing, and register itself
for coordinated startup/shutdown, without each one reinventing those four
things differently. Core Engine Framework is that substrate: the one
framework with zero dependencies of its own (ARCHITECTURE.md §5), so it
can be the dependency everything else safely shares. It's also the first
framework built end-to-end (ROADMAP.md Phase 1) precisely because nothing
after it can be genuinely "done" while depending on a Core Engine that
doesn't exist yet.

Per [DECISIONS.md](../DECISIONS.md) ADR-0008, Core Engine is specified as
a **polyglot contract**: the four capabilities below are defined
language-agnostically in [`CONTRACT.md`](./CONTRACT.md) and
[`schemas/`](./schemas/), with Python shipping first as the reference
implementation. A framework built in another language later implements
the same contract; it does not get to invent its own.

## Architecture

```
core/
├── CONTRACT.md          the language-agnostic interface spec (source of truth)
├── schemas/              JSON Schemas for the shared data shapes
├── python/               Python reference implementation (this is what's installed today)
│   └── avishkar_core/
│       ├── config.py      Config
│       ├── logging.py     Logger
│       ├── event_bus.py   EventBus
│       ├── registry.py    ModuleRegistry
│       └── errors.py      shared error types
└── examples/
    └── quickstart.py     runs all four together end to end
```

Internally, the four components have one intentional coupling:
`ModuleRegistry` uses `EventBus` to publish `core.module.registered` /
`.started` / `.stopped`, and both `EventBus` and `ModuleRegistry` use
`Logger` to log their own activity. No other cross-component coupling
exists — `Config` and `Logger` are each usable completely standalone. See
[`examples/quickstart.py`](./examples/quickstart.py) for all four wired
together the way a real framework would use them.

## Folder Structure
See the tree above. A second-language implementation would add a sibling
to `python/` (e.g. `typescript/`), never touch `CONTRACT.md` without an
ADR (ADR-0008 already anticipates this), and reuse the same `schemas/`.

## Naming Standards
Follows [STANDARDS.md](../STANDARDS.md) §3 platform-wide. Python module
names are `snake_case` (`event_bus.py`, not `eventBus.py`); the
distribution package is `avishkar-core`, the import package is
`avishkar_core`.

## Interfaces

**Config** — `load_config(defaults, config_path, env_prefix, overrides) -> Config`;
`Config.get(key, default=None)`, `.require(key)`, `.as_dict()`.

**Logger** — `get_logger(name) -> Logger`; `.debug/.info/.warning/.error/.critical(message, **fields)`,
`.bind(**fields) -> Logger`.

**EventBus** — `EventBus()`; `.subscribe(event_type, handler) -> Subscription`,
`.unsubscribe(subscription)`, `.publish(event_type, payload, source) -> Event`.

**ModuleRegistry** — `ModuleRegistry(event_bus=None)`;
`.register(manifest, instance=None, replace=False)`, `.get(name)`,
`.list(kind=None)`, `.unregister(name)`, `.start_all()`, `.stop_all()`.

Full signatures, error conditions, and semantics: [`CONTRACT.md`](./CONTRACT.md).
This section is the summary; CONTRACT.md is the source of truth.

## Extension Model
Core Engine itself is deliberately closed to extension — it's meant to
stay small and stable since everything depends on it (adding a fifth
capability requires an ADR, not a PR). What's open: (1) a new language
implementation of the existing contract, (2) any framework using
`ModuleRegistry.register()` to add itself to the platform's module graph,
(3) any framework defining its own event types on the shared `EventBus`
(namespaced by publisher, e.g. `agent-factory.blueprint.validated`) — the
bus itself needs no changes for a new event type to flow through it.

## Examples
[`examples/quickstart.py`](./examples/quickstart.py) — a toy framework
loads config, logs, registers with lifecycle hooks, and reacts to another
module's registration event. Runs standalone:

```bash
python core/examples/quickstart.py
```

Minimal Config + Logger only:

```python
from avishkar_core import get_logger, load_config

config = load_config(defaults={"router": {"timeout": 30}})
logger = get_logger("my-framework")

logger.info("starting", timeout=config.get("router.timeout"))
```

## Best Practices
- Get one `Logger` per module via `get_logger(__name__-equivalent)`, not
  a shared global — it's cheap and idempotent (STANDARDS.md-style single
  responsibility per call site).
- Use `Config.require()` for anything the module cannot run without;
  reserve `Config.get(key, default)` for genuinely optional settings. A
  silent `None` for a required setting is a bug waiting to happen.
- Register with `ModuleRegistry` if a module has real startup/shutdown
  work (open a connection, warm a cache) — don't register just to appear
  in a list; that's what `list()` without registration overhead is for
  once discovery-only needs arise (see Future Roadmap).
- `EventBus` is thread-safe within a single process (Avishkar OS Phase
  17.4 hardening, ADR-0024): `subscribe()`/`unsubscribe()`/`publish()`
  are internally locked. A subscribed handler still runs outside that
  lock, so a handler that raises or blocks doesn't corrupt the
  subscriber list, but a slow handler does delay delivery to the
  remaining handlers in that `publish()` call (synchronous delivery is
  unchanged from Phase 1 — see CONTRACT.md SS3). Not safe across
  multiple OS processes — this remains a single-process, in-memory bus.

## Anti-Patterns
- Reaching into another component's internals instead of going through
  its public interface (e.g. constructing a `Logger`'s private
  `_stdlib_logger` directly) — breaks the polyglot contract's promise
  that only the public interface is portable across implementations.
- Logging `Config.as_dict()` wholesale "to see what's configured" — a
  secret value in config becomes a plaintext log line. Log specific keys
  you need, never the whole document.
- Catching `AvishkarCoreError` broadly to suppress it instead of handling
  the specific error (`ConfigError`, `ModuleNotRegisteredError`, ...) —
  defeats the point of a typed error hierarchy.

## Future Roadmap
- Async variants of `EventBus.publish` / handler signatures, once a
  framework genuinely needs non-blocking event handling (YAGNI until
  then — see STANDARDS.md §1).
- Cross-process event delivery (today's `EventBus` is in-process only).
- A second language implementation (TypeScript, most likely, once
  `mcp-factory` or `n8n-factory` need it) conforming to `CONTRACT.md`.
- `documentation-factory`-driven doc-coverage check that this README
  itself stays honest as the implementation evolves.
- Discovery-only module registration (no lifecycle hooks required) if a
  real use case emerges that `list()` alone can't serve today.
