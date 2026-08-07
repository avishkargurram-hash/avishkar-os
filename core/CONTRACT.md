# Core Engine Framework — Language-Agnostic Contract

This is the source of truth for what "Core Engine" means, independent of
which language implements it. Per [DECISIONS.md](../DECISIONS.md)
ADR-0008, Python ships first
([`python/avishkar_core/`](./python/avishkar_core/)) as the reference
implementation — but conformance is judged against *this document and the
schemas in [`schemas/`](./schemas/)*, not against the Python source. A
future TypeScript (or other language) implementation must satisfy this
contract, not re-derive one from reading Python code.

Signatures below use a language-neutral pseudocode. `->` denotes a return
type; `throws` lists the error conditions an implementation must surface
in whatever way is idiomatic for its language (exceptions, `Result`
types, error returns — the *condition* is the contract, not the
mechanism).

---

## 1. Config

Layered configuration: `defaults < config file < environment variables <
explicit overrides`. Later layers override earlier ones key-by-key
(deep-merged for nested objects, not replaced wholesale). Once resolved, a
`Config` is **immutable** — no implementation may expose a mutating setter
on a resolved `Config`.

Each layer, before merging, must independently validate against
[`schemas/config.schema.json`](./schemas/config.schema.json).

```
load_config(
  defaults: ConfigDocument = {},
  config_path: string | null = null,
  env_prefix: string = "AVISHKAR_",
  overrides: ConfigDocument = {}
) -> Config
  throws ConfigError  # invalid JSON/file, schema violation, or a
                       # required() key (see below) missing after all
                       # layers are merged

Config.get(key: string, default: any = null) -> any
  # `key` is dot-separated for nested access, e.g. "router.timeout"

Config.require(key: string) -> any
  throws ConfigError  # if key is absent after all layers merged

Config.as_dict() -> ConfigDocument
  # A plain, read-only snapshot -- for passing to code outside the
  # Core Engine's own type system (e.g. a third-party library's config).
```

**Environment variable mapping:** `env_prefix` + uppercased, `.`-joined
key path with `.` replaced by `__` (double underscore), e.g. config key
`router.timeout` binds to env var `AVISHKAR_ROUTER__TIMEOUT`. Env values
are strings; implementations must attempt, in order: JSON parse (so
`"30"`, `"true"`, `"[1,2]"` decode to their typed values), falling back to
the raw string if JSON parsing fails.

**Secrets:** `Config` must never log its own contents at `INFO` level or
below — see [STANDARDS.md](../STANDARDS.md) §6. A `Config.get`/`require`
call is not itself a logged event.

**Immutability of returned values:** `Config.get`/`require` must never
return a reference a caller could mutate to corrupt the resolved config's
internal state. Concretely: nested objects come back as read-only mappings
and arrays come back as immutable sequences (the Python reference
implementation uses `MappingProxyType` and `tuple`, never `dict`/`list`),
not the language's default mutable collection types. `Config.as_dict()` is
the one escape hatch — it returns a plain, mutable, *disconnected*
snapshot for handing to code outside the Core Engine's type system.

---

## 2. Logger

Structured logging with two output modes — `text` (human-readable, for
local dev) and `json` (machine-parseable, matches
[`schemas/log-record.schema.json`](./schemas/log-record.schema.json), for
anywhere logs are aggregated). Mode is controlled by `AVISHKAR_LOG_FORMAT`
(`text` default, or `json`); minimum level by `AVISHKAR_LOG_LEVEL`
(default `INFO`).

```
get_logger(name: string) -> Logger
  # Idempotent: calling with the same `name` twice returns loggers that
  # share configuration (level, format) -- implementations must not
  # register duplicate output handlers on repeated calls.

Logger.debug(message: string, **fields) -> void
Logger.info(message: string, **fields) -> void
Logger.warning(message: string, **fields) -> void
Logger.error(message: string, exception: Error | null = null, **fields) -> void
Logger.critical(message: string, exception: Error | null = null, **fields) -> void

Logger.bind(**fields) -> Logger
  # Returns a logger that attaches `fields` (e.g. correlation_id) to
  # every subsequent record, without mutating the original logger.
```

Every emitted record — in either mode — must carry the fields required by
`log-record.schema.json` (`timestamp`, `level`, `module`, `message`
required; `correlation_id`, `fields`, `exception` present when
applicable).

---

## 3. EventBus

In-process, synchronous publish/subscribe. Cross-process/distributed event
delivery is explicitly out of scope for v1 — see Future Roadmap in
[README.md](./README.md).

```
EventBus.subscribe(event_type: string, handler: (Event) -> void) -> Subscription
  # event_type "*" subscribes to every event (for logging/audit use).

EventBus.unsubscribe(subscription: Subscription) -> void

EventBus.publish(event_type: string, payload: object, source: string) -> Event
  # Constructs and returns the Event envelope (see
  # schemas/event.schema.json), calling every matching handler
  # synchronously, in subscription order.
  # A handler that throws must not prevent remaining handlers from
  # running, and must not propagate to the caller of publish() --
  # implementations log the handler's error (via Logger, level ERROR)
  # and continue.
```

---

## 4. ModuleRegistry

Registration and lifecycle for every framework/agent/shelf-package that
wants to participate in coordinated startup/shutdown and be discoverable
by name. Registration is optional — a module that never needs lifecycle
hooks or cross-module discovery has no obligation to register.

```
ModuleRegistry.register(manifest: ModuleManifest, instance: any = null, replace: bool = false) -> void
  throws ModuleAlreadyRegisteredError  # if manifest.name is already
                                         # registered and replace=false
  throws DependencyDirectionError      # if manifest.dependencies
                                         # contains anything the
                                         # dependency-direction rule
                                         # (ARCHITECTURE.md SS5) forbids
                                         # (currently: nothing outside
                                         # the registry itself -- this
                                         # check is a placeholder until
                                         # an application registry
                                         # exists to violate against)
  # manifest must validate against schemas/module-manifest.schema.json.

ModuleRegistry.get(name: string) -> RegisteredModule
  throws ModuleNotRegisteredError

ModuleRegistry.list(kind: string | null = null) -> list[RegisteredModule]

ModuleRegistry.unregister(name: string) -> void

ModuleRegistry.start_all() -> void
  # Calls instance.on_start() (if the instance defines one) for every
  # registered module, in registration order. Publishes
  # "core.module.started" (payload: {name}) via EventBus after each.

ModuleRegistry.stop_all() -> void
  # Calls instance.on_stop() (if defined), in REVERSE registration
  # order. Publishes "core.module.stopped" per module.
```

---

## Cross-cutting rules

- **No component depends on another component's concrete implementation
  class** — only on this contract. The Python reference implementation's
  `EventBus` may internally use its own `Logger` instance, for example,
  but external callers never reach into another component's internals.
- **No component in Core Engine depends on anything outside `core/`** —
  see ARCHITECTURE.md §5. This is the one framework every other framework
  depends on; the reverse is a bug, not a design choice.
- **Conformance tests**: any new language implementation must pass a
  conformance suite exercising every method above against its documented
  error conditions before it's considered a valid Core Engine
  implementation (tracked in [README.md](./README.md)'s Future Roadmap —
  the Python implementation's own test suite is the seed for that
  eventual cross-language suite).
